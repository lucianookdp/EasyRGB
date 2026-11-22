"""Bateria de robustez: o que pode dar errado no PC de quem baixa o EasyRGB.

Arquivos corrompidos, pedidos estranhos na API, hardware diferente, códigos inválidos, efeitos com qualquer
número de LEDs, scripts do instalador e o servidor MCP recebendo lixo. Nada aqui mexe no hardware real nem
nos arquivos do usuário: tudo roda numa pasta temporária com dispositivos simulados.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["EASYRGB_NO_VENDORS"] = "1"
os.environ["EASYRGB_NO_EXIT"] = "1"
import rgb_controller as rc  # noqa: E402
from test_core import FakeClient, FakeDev, FakeMode, FakeZone, HAS_LIB, fake_pc  # noqa: E402

DATA_FILES = {"STATE_FILE": "last_state.json", "CLAUDE_FILE": "claude_color.json", "PC_FILE": "pc.json",
              "AUTO_FILE": "automations.json", "USER_PRESETS_FILE": "my_presets.json"}
GARBAGE = ["", "{", "[]", "null", '"texto"', "123", '{"palette": 5, "ui": null, "devices": "x"}',
           '{"games": "x", "schedule": {"a": 1}}', "\x00\xff lixo", '{"mcpServers": 1}']


class Isolated(unittest.TestCase):
    """Pasta de dados temporária: nada toca nos arquivos reais do usuário."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(APP / "palettes.json", self.tmp / "palettes.json")
        self.patches = [mock.patch.object(rc, "HERE", self.tmp),
                        mock.patch.object(rc, "PALETTES_FILE", self.tmp / "palettes.json")]
        self.patches += [mock.patch.object(rc, k, self.tmp / v) for k, v in DATA_FILES.items()]
        for p in self.patches:
            p.start()
        rc._hw_cache.clear()
        if hasattr(rc, "_pc_cache"):
            rc._pc_cache.update(key=None, v=None)

    def tearDown(self):
        rc.stop_effect()
        for p in self.patches:
            p.stop()
        if hasattr(rc, "_pc_cache"):
            rc._pc_cache.update(key=None, v=None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text):
        (self.tmp / name).write_bytes(text.encode("utf-8", errors="surrogateescape"))


# ------------------------------------------------------------------ arquivos corrompidos
class TestCorruptFiles(Isolated):
    """Arquivo salvo pela metade (PC desligou), editado à mão ou de uma versão antiga: o app tem que abrir."""

    def test_loaders_survive_garbage(self):
        loaders = [rc.load_state, rc.load_auto, rc.load_palettes, rc.load_pc, rc.load_claude, rc.user_presets]
        for name in DATA_FILES.values():
            for g in GARBAGE:
                self.write(name, g)
                for fn in loaders:
                    with self.subTest(file=name, content=g[:20], fn=fn.__name__):
                        fn()   # não pode lançar exceção

    def test_auto_always_has_the_expected_shape(self):
        for g in GARBAGE:
            self.write("automations.json", g)
            a = rc.load_auto()
            with self.subTest(content=g[:20]):
                self.assertIsInstance(a, dict)
                self.assertIsInstance(a.get("games", []), list)
                self.assertIsInstance(a.get("schedule", []), list)

    def test_palettes_ignore_broken_user_presets(self):
        for g in GARBAGE:
            self.write("my_presets.json", g)
            pal = rc.load_palettes()
            with self.subTest(content=g[:20]):
                self.assertIn("GTA VI", pal)
                self.assertTrue(all(isinstance(v, list) for v in pal.values()))

    def test_backup_restore_roundtrip_and_rejects_junk(self):
        rc.save_user_preset("Meu", ["#FF0000", "#0000FF"])
        b = rc.make_backup()
        self.assertEqual(b["easyrgb_backup"], 1)
        for junk in (None, [], "x", {"easyrgb_backup": 2}, {"look": {}}):
            with self.subTest(junk=junk), self.assertRaises(ValueError):
                rc.restore_backup(junk, apply_now=False)
        with mock.patch.object(rc, "sync_hotkeys"):
            done = rc.restore_backup(b, apply_now=False)
        self.assertIn("my_presets", done)
        self.assertTrue((self.tmp / "antes-de-restaurar.json").exists())


# ------------------------------------------------------------------ API recebendo qualquer coisa
POST_ROUTES = ["/api/apply", "/api/preview", "/api/effect", "/api/off", "/api/auto", "/api/quick", "/api/share",
               "/api/restore", "/api/claude", "/api/preset", "/api/setup", "/api/undo", "/api/autostart",
               "/api/update", "/api/mcp", "/api/connect"]
BAD_BODIES = [{}, {"colors": "zz"}, {"colors": ["#GGGGGG", None, 5]}, {"colors": ["#FF0000"], "brightness": "abc"},
              {"colors": ["#FF0000"], "devices": "x"}, {"colors": ["#FF0000"], "overrides": [1, 2]},
              {"colors": ["#FF0000"], "groups": "x"}, {"colors": ["#FF0000"], "on": True, "kind": "inexistente"},
              {"colors": ["#FF0000"], "on": True, "speed": "rapido"}, {"action": "nada", "value": {"x": 1}},
              {"code": "EASYRGB1-!!!"}, {"name": "x" * 5000, "colors": ["#FF0000"] * 500},
              {"games": "x"}, {"confirm": "nao"}, {"app": "inexistente"}]


class TestApiFuzz(Isolated):
    def setUp(self):
        super().setUp()
        self.devs = fake_pc()
        self.more = [mock.patch.object(rc, "client", return_value=FakeClient(self.devs)),
                     mock.patch.object(rc, "openrgb_running", return_value=True),
                     mock.patch.object(rc, "start_openrgb", return_value=True),
                     mock.patch.object(rc, "autostart_installed", return_value=False),
                     mock.patch.object(rc, "set_autostart", return_value=False),
                     mock.patch.object(rc, "install_update", return_value={"ok": False, "error": "teste"}),
                     mock.patch.object(rc, "undo_everything", return_value=[]),
                     mock.patch.object(rc, "sync_hotkeys")]
        for p in self.more:
            p.start()
        self.srv = rc.Server(("127.0.0.1", 0), rc.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        for p in self.more:
            p.stop()
        super().tearDown()

    def raw(self, path, data=None, ctype="application/json"):
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": ctype},
                                     method="GET" if data is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def alive(self):
        code, body = self.raw("/api/state")
        self.assertEqual(code, 200)
        json.loads(body)

    def test_every_route_answers_bad_input_with_json(self):
        import mcp_server
        with mock.patch.object(mcp_server, "connect_client", side_effect=ValueError("app desconhecido")):
            for route in POST_ROUTES:
                for body in BAD_BODIES:
                    with self.subTest(route=route, body=str(body)[:60]):
                        code, data = self.raw(route, json.dumps(body).encode())
                        self.assertIn(code, (200, 400, 404, 500))
                        out = json.loads(data)   # sempre JSON, nunca conexão cortada
                        if code != 200:
                            self.assertIn("error", out)
        self.alive()

    def test_body_that_is_not_json_or_not_an_object(self):
        for data in (b"{quebrado", b"\xff\xfe\x00", b"[1,2,3]", b'"so texto"', b"null", b""):
            for route in ("/api/apply", "/api/effect", "/api/preset", "/api/claude"):
                with self.subTest(route=route, data=data):
                    code, out = self.raw(route, data)
                    self.assertIn(code, (200, 400, 500))
                    json.loads(out)
        self.alive()

    def test_unknown_routes_and_methods(self):
        for path in ("/nada", "/api/nada", "/../app/pc.json", "/api/state/../../x", "/%00"):
            with self.subTest(path=path):
                code, _ = self.raw(path)
                self.assertIn(code, (200, 404))
        code, _ = self.raw("/api/nada", b"{}")
        self.assertEqual(code, 404)
        self.alive()

    def test_many_requests_at_once(self):
        errors = []

        def hit(i):
            try:
                body = json.dumps({"colors": ["#FF0000", "#00FF00"], "brightness": 10 + i % 90}).encode()
                code, _ = self.raw("/api/preview", body)
                if code != 200:
                    errors.append(code)
                code, _ = self.raw("/api/state")
                if code != 200:
                    errors.append(code)
            except Exception as e:   # noqa: BLE001
                errors.append(repr(e))
        threads = [threading.Thread(target=hit, args=(i,)) for i in range(24)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(errors, [])
        self.alive()

    def test_path_traversal_does_not_leak_files(self):
        (self.tmp / "segredo.txt").write_text("nao pode vazar", encoding="utf-8")
        for path in ("/../segredo.txt", "/..%2fsegredo.txt", "/app/../segredo.txt", "/segredo.txt"):
            with self.subTest(path=path):
                _, body = self.raw(path)
                self.assertNotIn(b"nao pode vazar", body)


# ------------------------------------------------------------------ hardware de todo tipo
def random_pc(rng):
    """PC inventado: tipos, zonas e LEDs variados (inclui zona sem LED e dispositivo de 1 LED)."""
    devs = []
    for i in range(rng.randint(1, 6)):
        zones = [FakeZone(f"Z{z}", rng.choice([0, 1, 1, 3, 8, 22, 94])) for z in range(rng.randint(1, 5))]
        modes = [FakeMode("Direct", 32, 1), FakeMode("Static", 32, 1)]
        if rng.random() < 0.5:
            modes.append(FakeMode("Breathing", 1, 1, 0, 10))
        devs.append(FakeDev(f"Dev{i} ção ✨", rng.choice([0, 1, 2, 4, 5, 6, 13, 19]), zones, modes))
    return devs


class TestAnyHardware(Isolated):
    def test_plan_colors_for_random_pcs(self):
        rng = random.Random(42)
        for _ in range(300):
            devs = random_pc(rng)
            ids = [i for i in range(len(devs)) if rng.random() < 0.85]
            pal = [tuple(rng.randrange(256) for _ in range(3)) for _ in range(rng.randint(1, 6))]
            mode = rng.choice(["gradiente", "alternado", "zona"])
            ov = {str(i): {str(z): "#123456" for z in range(rng.randint(0, 3))} for i in ids if rng.random() < 0.3}
            groups = [{"ids": ids[:rng.randint(0, len(ids))], "mode": rng.choice(["mirror", "span", "separate"])}]
            plan = rc.plan_colors(devs, ids, pal, mode, rng.choice([0.0, 0.37]), ov, groups)
            for i in ids:
                n = sum(len(z.leds) for z in devs[i].zones)
                self.assertEqual(len(plan.get(i, [])), n)
                for c in plan.get(i, []):
                    self.assertTrue(all(0 <= v <= 255 for v in c))

    @unittest.skipUnless(HAS_LIB, "precisa da biblioteca openrgb-python")
    def test_apply_on_random_pcs(self):
        rng = random.Random(7)
        for _ in range(60):
            devs = random_pc(rng)
            with mock.patch.object(rc, "client", return_value=FakeClient(devs)):
                rep = rc.apply([(255, 0, 0), (0, 0, 255)], rng.randint(0, 100), rng.choice(["gradiente", "zona"]),
                               persist=False)
            self.assertTrue(all(r["ok"] for r in rep), rep)

    def test_zero_devices(self):
        with mock.patch.object(rc, "client", return_value=FakeClient([])):
            self.assertEqual(rc.plan_colors([], [], [(1, 2, 3)], "gradiente", 0, {}, []), {})
            if HAS_LIB:
                self.assertEqual(rc.apply([(1, 2, 3)], persist=False), [])


class TestEffectsMatrix(unittest.TestCase):
    """Todo efeito, com qualquer quantidade de LEDs, paleta e velocidade, devolve cores válidas."""

    def test_every_effect_every_size(self):
        ctx = {"level": 0.7, "shift": 0.2, "stars": {}, "keys": None, "dir": "centro", "shot": None, "idx": 0}
        for kind in list(rc.EFFECTS) + ["static", "desconhecido"]:
            for n in (0, 1, 2, 7, 94):
                for pal in ([(255, 0, 0)], [(255, 0, 0), (0, 0, 255)], rc.RAINBOW):
                    for speed in (1, 3, 10):
                        cols = [(10, 20, 30)] * n
                        pos = [((i + 0.5) / max(1, n), 0.5) for i in range(n)]
                        for kb in (False, True):
                            with self.subTest(kind=kind, n=n, pal=len(pal), speed=speed, kb=kb):
                                out = rc.effect_colors(kind, pal, cols, pos, kb, 2.5, speed, dict(ctx, idx=n))
                                self.assertEqual(len(out), n)
                                for c in out:
                                    self.assertEqual(len(c), 3)
                                    self.assertTrue(all(isinstance(v, int) and 0 <= v <= 255 for v in c), c)

    def test_effect_map_ignores_junk(self):
        m = rc.effect_map("nada", {"pfx": {"1": "onda", "x": 5, "2": None}, "fxdevs": "x"}, [0, 1, 2])
        self.assertEqual(m, {0: "static", 1: "onda", 2: "static"})


# ------------------------------------------------------------------ códigos de compartilhar
class TestShareCodeFuzz(unittest.TestCase):
    def test_garbage_codes_raise_value_error(self):
        import base64
        bad = ["", "x", "EASYRGB1-", "EASYRGB1-!!!!", "EASYRGB1-" + "A" * 10000, "MEURGB1-%%%",
               "EASYRGB1-" + base64.urlsafe_b64encode(b"nao e json").decode(),
               "EASYRGB1-" + base64.urlsafe_b64encode(b'{"c": []}').decode(),
               "EASYRGB1-" + base64.urlsafe_b64encode(b'[1, 2]').decode(),
               "EASYRGB1-" + base64.urlsafe_b64encode(b'{"c": ["#FF0000"], "b": "muito"}').decode()]
        for code in bad:
            with self.subTest(code=code[:30]), self.assertRaises(ValueError):
                rc.read_share_code(code)

    def test_roundtrip_with_unicode_name(self):
        code = rc.share_code({"palette": ["#FF0000", "#00FF00"], "mode": "zona", "brightness": 55, "name": "Pôr do Sol ✨",
                              "ui": {"effect": "onda", "speed": 7}})
        look = rc.read_share_code(code)
        self.assertEqual(look["colors"], ["#FF0000", "#00FF00"])
        self.assertEqual(look["brightness"], 55)


# ------------------------------------------------------------------ servidor MCP recebendo lixo
class TestMcpFuzz(unittest.TestCase):
    def setUp(self):
        import mcp_server
        self.m = mcp_server
        st = {"connected": True, "palettes": {"GTA VI": ["#F1047A", "#BB08F7"]},
              "devices": [{"id": 0, "name": "Board", "type": "MOTHERBOARD", "zones": [{"name": "A", "leds": 6}]}],
              "last": {"palette": ["#111111"], "ui": {}}, "pc": None}
        self.p = [mock.patch.object(mcp_server, "_call", side_effect=lambda path, body=None, timeout=60:
                                    st if path == "/api/state" else {"ok": True, "report": []}),
                  mock.patch.object(mcp_server, "ensure_app")]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_tools_never_crash(self):
        weird = [None, {}, {"colors": "x"}, {"colors": [1, 2]}, {"preset": 5}, {"brightness": "x"}, {"percent": "abc"},
                 {"on": "talvez"}, {"peripheral_effects": "onda"}, {"effect": ["x"]}, {"speed": -5}]
        for tool in [t["name"] for t in self.m.TOOLS]:
            for args in weird:
                with self.subTest(tool=tool, args=args):
                    r = self.m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": tool, "arguments": args}})
                    self.assertIn("result", r)   # erro vira resposta para a IA, não queda do servidor
                    self.assertIn("content", r["result"])

    def test_protocol_garbage(self):
        for msg in ({}, {"id": 1}, {"id": 1, "method": None}, {"id": 1, "method": "tools/call"},
                    {"id": 1, "method": "tools/call", "params": "x"}, {"id": "abc", "method": "ping"}):
            with self.subTest(msg=msg):
                r = self.m.handle(msg)
                self.assertTrue(r is None or "result" in r or "error" in r)


# ------------------------------------------------------------------ instalador e scripts
class TestInstallScripts(unittest.TestCase):
    def test_powershell_scripts_parse(self):
        ps1 = sorted(ROOT.glob("*.ps1"))
        self.assertTrue(ps1)
        if not shutil.which("powershell"):
            self.skipTest("sem PowerShell")
        for f in ps1:
            cmd = ("$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("
                   f"'{f}',[ref]$null,[ref]$e); $e.Count")
            out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), text=True,
                                 timeout=60).stdout.strip()
            with self.subTest(script=f.name):
                self.assertEqual(out, "0")

    def test_batch_file_uses_windows_line_endings(self):
        raw = (ROOT / "EasyRGB.bat").read_bytes()
        self.assertIn(b"\r\n", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))   # cmd.exe se perde com LF sozinho

    def test_inno_setup_references_existing_files(self):
        iss = ROOT / "installer" / "EasyRGB.iss"
        if not iss.exists():
            self.skipTest("sem instalador")
        import re
        text = iss.read_text(encoding="utf-8", errors="ignore")
        for src in re.findall(r'Source:\s*"([^"]+)"', text):
            if "{" in src or "dist" in src.lower():
                continue   # gerados no build
            with self.subTest(src=src):
                self.assertTrue((iss.parent / src).exists() or (ROOT / src).exists(), src)

    def test_build_script_compiles(self):
        for f in (ROOT / "tools").glob("*.py"):
            with self.subTest(f=f.name):
                compile(f.read_text(encoding="utf-8"), str(f), "exec")

    def test_prompts_match_everywhere(self):
        """O prompt de configuração em inglês é o mesmo no README, no START-HERE e no botão do app."""
        import re
        html = (APP / "index.html").read_text(encoding="utf-8")
        m = re.search(r"Set up EasyRGB on my PC[^`\n]*", html)
        if not m:
            self.skipTest("prompt não está no app")
        prompt = m.group(0)
        self.assertIn(prompt, (ROOT / "START-HERE.txt").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ código: sem erro bobo
class TestCodeHygiene(unittest.TestCase):
    def test_python_compiles_without_warnings(self):
        import warnings
        for f in list(APP.glob("*.py")) + list((ROOT / "tests").glob("*.py")) + list((ROOT / "tools").glob("*.py")):
            with self.subTest(f=f.name), warnings.catch_warnings():
                warnings.simplefilter("error")   # ex.: "\W" num texto vira erro no Python novo
                compile(f.read_text(encoding="utf-8"), str(f), "exec")

    def test_no_command_flashes_a_window(self):
        """Toda janela de comando que o app abre fica escondida: uma janela piscando tira o foco do jogo."""
        import ast
        for f in list(APP.glob("*.py")) + list((ROOT / "tests").glob("*.py")):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and                         n.func.attr in ("run", "Popen", "call", "check_output") and                         getattr(n.func.value, "id", "") == "subprocess":
                    if any(k.arg == "creationflags" for k in n.keywords):
                        continue
                    first = n.args[0] if n.args else None
                    cmd = ast.unparse(first) if first is not None else ""
                    if "Edge" in cmd or "edge" in cmd:
                        continue   # a janela do app é para aparecer
                    with self.subTest(file=f.name, line=n.lineno):
                        self.fail(f"subprocess sem creationflags (pode piscar janela): {cmd[:60]}")

    def test_javascript_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("sem Node.js")
        import re
        html = (APP / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertTrue(scripts)
        tmp = Path(tempfile.mkdtemp())
        try:
            for i, s in enumerate(scripts):
                f = tmp / f"s{i}.js"
                f.write_text(s, encoding="utf-8")
                r = subprocess.run([node, "--check", str(f)], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), text=True, timeout=60)
                with self.subTest(script=i):
                    self.assertEqual(r.returncode, 0, r.stderr[-800:])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_json_resources_are_valid(self):
        for f in [APP / "palettes.json"] + list((APP / "lang").glob("*.json") if (APP / "lang").exists() else []):
            with self.subTest(f=f.name):
                data = json.loads(f.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)
        for name, cols in json.loads((APP / "palettes.json").read_text(encoding="utf-8")).items():
            with self.subTest(preset=name):
                self.assertTrue(cols)
                self.assertEqual(len(rc.parse_colors(cols)), len(cols))


# ------------------------------------------------------------------ segurança
class TestSecurity(TestApiFuzz):
    """Um site aberto no navegador não pode mandar comandos para o EasyRGB (CSRF / DNS rebinding)."""

    def req(self, path, body=None, headers=None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers=h, method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_listens_only_on_this_pc(self):
        src = (APP / "rgb_controller.py").read_text(encoding="utf-8")
        self.assertIn('Server(("127.0.0.1", UI_PORT)', src)
        self.assertNotIn('"0.0.0.0"', src)

    def test_websites_are_blocked(self):
        port = self.srv.server_address[1]
        evil = [{"Origin": "http://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"},
                {"Host": f"evil.example:{port}"}, {"Host": "127.0.0.1"}, {"Origin": f"http://127.0.0.1:{port + 1}"}]
        for h in evil:
            with self.subTest(headers=h):
                self.assertEqual(self.req("/api/state", headers=h), 403)
                self.assertEqual(self.req("/", headers=h) if "Host" in h else 403, 403)
                self.assertEqual(self.req("/api/apply", {"colors": ["#FF0000"]}, h), 403)

    def test_destructive_actions_cannot_come_from_a_site(self):
        with mock.patch.object(rc, "undo_everything") as undo, mock.patch.object(rc, "install_update") as upd:
            self.assertEqual(self.req("/api/undo", {"confirm": "DESFAZER", "delete_data": True},
                                      {"Origin": "https://evil.example"}), 403)
            self.assertEqual(self.req("/api/update", {}, {"Origin": "https://evil.example"}), 403)
            undo.assert_not_called()
            upd.assert_not_called()

    def test_form_posts_are_refused(self):
        """Um <form> de outro site só manda text/plain ou form-urlencoded: o EasyRGB exige JSON."""
        for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
            with self.subTest(ctype=ctype):
                self.assertEqual(self.req("/api/off", {}, {"Content-Type": ctype}), 415)

    def test_the_app_itself_still_works(self):
        port = self.srv.server_address[1]
        for h in ({}, {"Origin": f"http://127.0.0.1:{port}"}, {"Origin": f"http://localhost:{port}",
                                                               "Host": f"localhost:{port}"},
                  {"Sec-Fetch-Site": "same-origin"}):
            with self.subTest(headers=h):
                self.assertEqual(self.req("/api/state", headers=h), 200)
                self.assertEqual(self.req("/api/preview", {"colors": ["#FF0000"]}, h), 200)

    def test_huge_or_negative_content_length(self):
        import http.client
        port = self.srv.server_address[1]
        for cl in ("-5", "abc", "99999999999"):
            with self.subTest(cl=cl):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                c.putrequest("POST", "/api/apply")
                c.putheader("Content-Type", "application/json")
                c.putheader("Content-Length", cl)
                c.endheaders()
                c.send(b"{}")
                try:
                    self.assertIn(c.getresponse().status, (200, 400, 500))
                except (ConnectionError, http.client.HTTPException, TimeoutError):
                    pass   # o servidor pode recusar a conexão; o importante é continuar de pé
                c.close()
        self.alive()


class TestErrorMessages(TestApiFuzz):
    """Erro vira mensagem que a pessoa entende; o detalhe técnico fica só no log."""

    def test_friendly_messages(self):
        self.assertEqual(rc.friendly_error(ValueError("Dê um nome ao preset")), (400, "Dê um nome ao preset"))
        code, msg = rc.friendly_error(ConnectionResetError())
        self.assertEqual(code, 503)
        self.assertIn("OpenRGB", msg)
        code, msg = rc.friendly_error(KeyError("x"))
        self.assertEqual(code, 500)
        self.assertNotIn("KeyError", msg)

    def test_unexpected_error_is_logged_not_shown(self):
        with mock.patch.object(rc, "apply", side_effect=KeyError("detalhe interno")):
            code, data = self.raw("/api/apply", json.dumps({"colors": ["#FF0000"]}).encode())
        out = json.loads(data)
        self.assertEqual(code, 500)
        self.assertNotIn("detalhe interno", out["error"])
        log = (self.tmp / "easyrgb.log").read_text(encoding="utf-8")
        self.assertIn("detalhe interno", log)
        self.assertIn("POST /api/apply", log)

    def test_odd_numbers_are_accepted(self):
        for bri in ("80", 80.6, "abc", None, -10, 999):
            with self.subTest(bri=bri):
                code, _ = self.raw("/api/preview", json.dumps({"colors": ["#FF0000"], "brightness": bri}).encode())
                self.assertEqual(code, 200)

    def test_openrgb_down_gives_a_clear_message(self):
        with mock.patch.object(rc, "client", side_effect=ConnectionRefusedError()):
            code, data = self.raw("/api/apply", json.dumps({"colors": ["#FF0000"]}).encode())
        self.assertEqual(code, 503)
        self.assertIn("Reconectar", json.loads(data)["error"])


class TestUpdateSafety(Isolated):
    def test_only_downloads_from_the_official_repo(self):
        info = {"available": True, "can_install": True, "latest": "9.9.9",
                "url": "https://evil.example/EasyRGB-windows.zip"}
        with mock.patch.object(rc, "check_update", return_value=info), mock.patch.object(rc, "FROZEN", True), \
             mock.patch("urllib.request.urlopen") as net:
            with self.assertRaises(RuntimeError):
                rc.install_update()
            net.assert_not_called()

    def test_zip_cannot_write_outside_its_folder(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../../fora.txt", "x")
            z.writestr("EasyRGB/EasyRGB.exe", "x")
        info = {"available": True, "can_install": True, "latest": "9.9.9",
                "url": f"https://github.com/{rc.REPO}/releases/download/v9.9.9/EasyRGB-windows.zip"}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        with mock.patch.object(rc, "check_update", return_value=info), mock.patch.object(rc, "FROZEN", True), \
             mock.patch("urllib.request.urlopen", return_value=Resp(buf.getvalue())), \
             mock.patch.object(rc, "_run_after_exit") as run:
            with self.assertRaises(RuntimeError):
                rc.install_update()
            run.assert_not_called()


class FakeDownload:
    """Resposta de download falsa (o conteúdo de um zip)."""
    def __init__(self, data):
        import io
        self.b = io.BytesIO(data)

    def read(self, *a):
        return self.b.read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestSourceUpdate(Isolated):
    """Quem roda pelo código (zip do GitHub ou pasta clonada) também atualiza sozinho, sem perder os dados."""

    def setUp(self):
        super().setUp()
        self.root = self.tmp / "EasyRGB"
        (self.root / "app").mkdir(parents=True)
        (self.root / "app" / "rgb_controller.py").write_text("velho", encoding="utf-8")
        (self.root / "app" / "pc.json").write_text('{"meu": "perfil"}', encoding="utf-8")
        self.info = {"available": True, "can_install": True, "latest": "9.9.9", "tag": "v9.9.9"}
        self.p2 = [mock.patch.object(rc, "ROOT", self.root), mock.patch.object(rc, "FROZEN", False),
                   mock.patch.object(rc, "check_update", return_value=self.info),
                   mock.patch.object(rc, "_run_after_exit")]
        for x in self.p2:
            x.start()

    def tearDown(self):
        for x in self.p2:
            x.stop()
        super().tearDown()

    def zip_of(self, files):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, text in files.items():
                z.writestr(name, text)
        return buf.getvalue()

    def test_zip_update_replaces_code_and_keeps_data(self):
        data = self.zip_of({"EasyRGB-9.9.9/app/rgb_controller.py": "novo", "EasyRGB-9.9.9/README.md": "leia"})
        with mock.patch("urllib.request.urlopen", return_value=FakeDownload(data)) as net:
            out = rc.install_update()
        self.assertTrue(out["ok"])
        self.assertIn(f"github.com/{rc.REPO}/archive/refs/tags/v9.9.9.zip", net.call_args[0][0].full_url)
        self.assertEqual((self.root / "app" / "rgb_controller.py").read_text(encoding="utf-8"), "novo")
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), "leia")
        self.assertEqual(json.loads((self.root / "app" / "pc.json").read_text(encoding="utf-8")), {"meu": "perfil"})
        rc._run_after_exit.assert_called_once()   # fecha e abre de novo com o código novo

    def test_zip_update_rejects_tricks(self):
        bad = self.zip_of({"../../fora.txt": "x", "EasyRGB-9.9.9/app/rgb_controller.py": "novo"})
        with mock.patch("urllib.request.urlopen", return_value=FakeDownload(bad)), self.assertRaises(RuntimeError):
            rc.install_update()
        self.assertEqual((self.root / "app" / "rgb_controller.py").read_text(encoding="utf-8"), "velho")
        self.info["tag"] = "v1; rm -rf /"
        with mock.patch("urllib.request.urlopen") as net, self.assertRaises(RuntimeError):
            rc.install_update()
        net.assert_not_called()

    def test_git_folder_uses_git_pull(self):
        (self.root / ".git").mkdir()
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd[3:])
            return subprocess.CompletedProcess(cmd, 0, stdout="main" if "rev-parse" in cmd else "", stderr="")
        with mock.patch("shutil.which", return_value="git"), \
             mock.patch.object(rc.subprocess, "run", side_effect=fake_run):
            self.assertTrue(rc.install_update()["ok"])
        self.assertIn(["pull", "--ff-only", "origin", "main"], calls)

    def test_git_folder_with_local_changes_is_not_touched(self):
        (self.root / ".git").mkdir()

        def fake_run(cmd, **kw):
            out = " M app/index.html" if "status" in cmd else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        with mock.patch("shutil.which", return_value="git"), \
             mock.patch.object(rc.subprocess, "run", side_effect=fake_run) as run, self.assertRaises(RuntimeError):
            rc.install_update()
        self.assertFalse(any("pull" in c[0][0] for c in run.call_args_list))
        rc._run_after_exit.assert_not_called()


class TestVendorKeepalive(Isolated):
    """O G HUB volta ao perfil dele depois de ficar ocioso: o EasyRGB repinta o teclado quando a pessoa volta."""

    def setUp(self):
        super().setUp()
        import vendors
        kb = FakeDev("PRO Gaming Keyboard", 5, [FakeZone("Keyboard", 2)], [FakeMode("Direct", 32, 1)])
        kb.leds = [type("L", (), {"name": "Key: A"})(), type("L", (), {"name": "Key: S"})()]
        kb.metadata = type("M", (), {"vendor": "Logitech"})()
        self.devs = fake_pc()[:1] + [kb]
        (self.tmp / "last_state.json").write_text(json.dumps({
            "palette": ["#F1047A", "#0B32F4"], "brightness": 100, "mode": "gradiente", "devices": None,
            "overrides": {}, "groups": [], "hw": {}, "ui": {"effect": "static", "pfx": {}}}), encoding="utf-8")
        self.applied = []
        self.p3 = [mock.patch.object(rc, "client", return_value=FakeClient(self.devs)),
                   mock.patch.object(rc, "vendor_route", side_effect=lambda d: object() if d is kb else None),
                   mock.patch.object(rc, "apply", side_effect=lambda *a, **k: self.applied.append((a, k)) or [])]
        for x in self.p3:
            x.start()
        rc._lights.update(off=False, preview=0.0, keep=0.0, idle=False)
        rc._auto["game"] = None
        rc._effect["on"] = False

    def tearDown(self):
        for x in self.p3:
            x.stop()
        rc._lights.update(off=False, preview=0.0, keep=0.0, idle=False)
        super().tearDown()

    def run_at(self, t, idle=0):
        with mock.patch.object(rc, "idle_seconds", return_value=idle):
            return rc.vendor_keepalive(now=t)

    def test_repaints_only_the_vendor_device_every_10s(self):
        self.assertTrue(self.run_at(1000))
        self.assertEqual(self.applied[-1][0][3], [1])   # só o teclado do G HUB, não a placa
        self.assertFalse(self.applied[-1][1]["persist"])
        self.assertFalse(self.run_at(1005))
        self.assertTrue(self.run_at(1011))

    def test_forced_repaint_skips_the_10s_wait(self):
        self.assertTrue(self.run_at(1000))
        with mock.patch.object(rc, "idle_seconds", return_value=0):
            self.assertTrue(rc.vendor_keepalive(now=1002, force=True))   # o G HUB pode ter reassumido agora

    def test_respects_idle_and_repaints_on_return(self):
        self.assertTrue(self.run_at(1000))
        self.assertFalse(self.run_at(1011, idle=300))   # ocioso: o G HUB pode apagar
        self.assertTrue(self.run_at(1012, idle=0))      # voltou: repinta na hora

    def test_never_fights_the_person(self):
        rc._lights.update(off=False, preview=995.0)
        self.assertFalse(self.run_at(1000))             # pré-visualizando na tela
        rc._lights["preview"] = 0.0
        rc._effect["on"] = True
        (self.tmp / "last_state.json").write_text(json.dumps({
            "palette": ["#F1047A"], "ui": {"effect": "static", "pfx": {"1": "onda"}}}), encoding="utf-8")
        self.assertFalse(self.run_at(1000))             # o efeito já está pintando o teclado
        self.assertEqual(self.applied, [])

    def test_lights_off_stay_off(self):
        """Apagou as luzes e o G HUB reacendeu o teclado com o perfil dele: apaga de novo, nunca acende o visual."""
        rc._lights["off"] = True
        with mock.patch.object(rc, "vendor_off", return_value=True) as off:
            self.assertTrue(self.run_at(1000))
            rc.restore_look()
        self.assertEqual(off.call_count, 2)
        self.assertEqual(self.applied, [])
        self.assertTrue(rc._lights["off"])

    def test_game_mode_keeps_the_game_palette(self):
        rc._auto["game"] = {"process": "cs2.exe", "look": {"palette": ["#FF0000"], "overrides": {}, "hw": {}}}
        try:
            self.assertTrue(self.run_at(1000))
            self.assertEqual(self.applied[-1][0][0], [(255, 0, 0)])   # paleta do jogo, não a salva
            with mock.patch.object(rc, "apply_saved") as saved:
                rc.restore_look()                                       # G HUB reabriu durante o jogo
            self.assertEqual(saved.call_args[1]["palette"], ["#FF0000"])
        finally:
            rc._auto["game"] = None

    def test_restore_outside_game_uses_saved_look(self):
        with mock.patch.object(rc, "apply_saved") as saved:
            self.assertTrue(rc.restore_look())
        saved.assert_called_once_with()

    def test_turning_off_blocks_until_turned_on(self):
        with mock.patch.object(rc, "start_effect"):
            rc._lights["off"] = True
            rc.apply_saved()
        self.assertFalse(rc._lights["off"])


class TestUpdaterSurvivesAppExit(unittest.TestCase):
    """O atualizador precisa continuar vivo depois que o EasyRGB fecha (aberto pela tarefa do Windows, o
    EasyRGB leva junto tudo o que abriu): ele é aberto pelo WMI, fora do EasyRGB, e escondido."""

    def test_launches_through_wmi_hidden(self):
        with mock.patch.object(rc.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run,              mock.patch.object(rc.subprocess, "Popen") as popen, mock.patch.object(rc, "quit_app_now"):
            rc._run_after_exit(Path(r"C:\Temp\O'Brientualizar.ps1"))
        ps = run.call_args[0][0][-1]
        self.assertIn("Win32_Process -MethodName Create", ps)
        self.assertIn("ShowWindow=[uint16]0", ps)
        self.assertIn("O''Brien", ps)            # caminho com apóstrofo não quebra o comando
        popen.assert_not_called()

    def test_falls_back_if_wmi_fails(self):
        with mock.patch.object(rc.subprocess, "run", return_value=subprocess.CompletedProcess([], 9)),              mock.patch.object(rc.subprocess, "Popen") as popen, mock.patch.object(rc, "quit_app_now"):
            rc._run_after_exit(Path(r"C:\Temptualizar.ps1"))
        popen.assert_called_once()


class TestPowerShellQuoting(unittest.TestCase):
    def test_apostrophes_in_paths(self):
        self.assertEqual(rc._ps(r"C:\Users\O'Brien\EasyRGB"), r"C:\Users\O''Brien\EasyRGB")
        if not shutil.which("powershell"):
            self.skipTest("sem PowerShell")
        path = r"C:\Users\O'Brien; Remove-Item x\EasyRGB"
        out = subprocess.run(["powershell", "-NoProfile", "-Command", f"Write-Output '{rc._ps(path)}'"],
                             capture_output=True, text=True, timeout=60,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        self.assertEqual(out, path)   # vira texto, nunca comando

    def test_temp_scripts_have_unique_names(self):
        a = rc._temp_script("easyrgb_teste_", "Write-Output 1")
        b = rc._temp_script("easyrgb_teste_", "Write-Output 1")
        try:
            self.assertNotEqual(a, b)
        finally:
            a.unlink()
            b.unlink()


class TestNoSecretsInRepo(unittest.TestCase):
    def test_no_keys_or_tokens_committed(self):
        import re
        if not shutil.which("git"):
            self.skipTest("sem git")
        files = [f for f in subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                            text=True).stdout.split(chr(0)) if f]
        pats = [r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"sk-[A-Za-z0-9]{20,}",
                r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"xox[baprs]-[A-Za-z0-9-]{10,}"]
        for f in files:
            p = ROOT / f
            if p.suffix.lower() in (".png", ".ico", ".exe", ".zip", ".dll"):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            for pat in pats:
                with self.subTest(file=f, pattern=pat):
                    self.assertIsNone(re.search(pat, text))

    def test_private_files_are_ignored(self):
        ign = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for name in ("pc.json", "last_state.json", "automations.json", "my_presets.json", "claude_color.json",
                     "*.log", "app/lib/"):
            with self.subTest(name=name):
                self.assertIn(name, ign)


if __name__ == "__main__":
    unittest.main()
