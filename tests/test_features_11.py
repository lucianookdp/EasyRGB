"""Assistente da primeira vez, atualização automática e pontes Razer / SteelSeries / Corsair (sem hardware)."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP))
os.environ["EASYRGB_NO_VENDORS"] = "1"
import rgb_controller as rc  # noqa: E402
import vendors_more as vm  # noqa: E402


class FakeServer:
    """Servidor HTTP local que grava o que recebe (imita a Chroma SDK ou o GameSense)."""

    def __init__(self, reply=lambda method, path, body: {}):
        calls = self.calls = []

        class H(BaseHTTPRequestHandler):
            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"null")
                calls.append((self.command, self.path, body))
                data = json.dumps(reply(self.command, self.path, body)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            do_GET = do_POST = do_PUT = do_DELETE = _do

            def log_message(self, *a):
                pass
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class Led:
    def __init__(self, name):
        self.name = name


KEYS = ["Key: Escape", "Key: A", "Key: Space", "Key: Number Pad 0"]
COLS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (10, 20, 30)]


# ------------------------------------------------------------------ Razer
class TestRazer(unittest.TestCase):
    def setUp(self):
        self.s = FakeServer(lambda m, p, b: {"sessionid": 1, "uri": f"http://127.0.0.1:{self.s.port}/chromasdk"}
                            if m == "POST" else {"result": 0})
        self.b = vm.RazerBridge()
        self.b.BASE = f"http://127.0.0.1:{self.s.port}/razer/chromasdk"
        self.p = mock.patch.object(vm.time, "sleep")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.s.close()

    def test_session_and_keyboard_grid(self):
        self.assertTrue(self.b.available())
        self.assertTrue(self.b.paint_keys([*KEYS], COLS))
        init = next(c for c in self.s.calls if c[0] == "POST")
        self.assertEqual(init[2]["title"], "EasyRGB")
        put = next(c for c in self.s.calls if c[0] == "PUT" and c[1].endswith("/keyboard"))
        grid = put[2]["param"]
        self.assertEqual(put[2]["effect"], "CHROMA_CUSTOM")
        self.assertEqual((len(grid), len(grid[0])), (6, 22))
        self.assertEqual(grid[0][1], vm.bgr((255, 0, 0)))   # Esc na coluna 1 da Razer
        self.assertEqual(vm.bgr((1, 2, 3)), 0x030201)        # a Chroma usa BGR

    def test_all_lights_static_and_no_spam(self):
        dev = self.b.devices(None)[0]
        self.assertEqual(dev.backend, "razer")
        dev.set_colors([(10, 20, 30)])
        n = len([c for c in self.s.calls if c[0] == "PUT"])
        self.assertEqual(n, len(set(vm.RazerBridge.TARGETS.values())))
        dev.set_colors([(10, 20, 30)])   # mesma cor logo em seguida: não reenvia
        self.assertEqual(len([c for c in self.s.calls if c[0] == "PUT"]), n)
        self.b.stop()
        self.assertEqual(self.s.calls[-1][0], "DELETE")


# ------------------------------------------------------------------ SteelSeries
class TestSteelSeries(unittest.TestCase):
    def setUp(self):
        self.s = FakeServer()
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "coreProps.json").write_text(json.dumps({"address": f"127.0.0.1:{self.s.port}"}), encoding="utf-8")
        self.p = mock.patch.object(vm.SteelSeriesBridge, "props", staticmethod(lambda: self.tmp / "coreProps.json"))
        self.p.start()
        self.b = vm.SteelSeriesBridge()

    def tearDown(self):
        self.p.stop()
        self.s.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_register_and_bitmap(self):
        self.assertTrue(self.b.installed() and self.b.available())
        self.assertTrue(self.b.paint_keys(KEYS, COLS))
        paths = [c[1] for c in self.s.calls]
        self.assertEqual(paths[:2], ["/game_metadata", "/bind_game_event"])
        ev = [c for c in self.s.calls if c[1] == "/game_event"][-1][2]
        self.assertEqual(len(ev["data"]["frame"]["bitmap"]), 22 * 6)
        self.assertEqual(ev["data"]["frame"]["bitmap"][0], [255, 0, 0])   # Esc no canto
        v1 = ev["data"]["value"]
        self.b.paint_keys(KEYS, COLS)
        v2 = [c for c in self.s.calls if c[1] == "/game_event"][-1][2]["data"]["value"]
        self.assertNotEqual(v1, v2)   # o GameSense só repinta quando o valor muda

    def test_not_installed(self):
        with mock.patch.object(vm.SteelSeriesBridge, "props", staticmethod(lambda: self.tmp / "nao.json")):
            self.assertFalse(vm.SteelSeriesBridge().available())


# ------------------------------------------------------------------ Corsair
class FakeICUE:
    """Imita a iCUESDK.x64_2019.dll: um teclado com 3 LEDs."""

    def __init__(self):
        self.colors = None

    def CorsairConnect(self, cb, ctx):
        ev = vm._CSessionStateChanged(state=vm.CONNECTED)
        cb(None, vm.ctypes.pointer(ev))

    def CorsairGetDevices(self, flt, size, arr, n):
        arr[0].type, arr[0].id, arr[0].model, arr[0].ledCount = 0x1, b"{kb-1}", b"K70 RGB", 3
        n._obj.value = 1

    def CorsairGetLedPositions(self, dev_id, size, pos, n):
        for i, (x, y) in enumerate([(0, 0), (50, 0), (100, 20)]):
            pos[i].id, pos[i].cx, pos[i].cy = 100 + i, x, y
        n._obj.value = 3

    def CorsairRequestControl(self, dev_id, level):
        return 0

    def CorsairSetLedColors(self, dev_id, size, arr):
        self.colors = [(arr[i].id, arr[i].r, arr[i].g, arr[i].b) for i in range(size)]

    def CorsairDisconnect(self):
        pass


class TestCorsair(unittest.TestCase):
    def test_struct_sizes_match_the_sdk(self):
        self.assertEqual(vm.ctypes.sizeof(vm._CDeviceInfo), 396)
        self.assertEqual(vm.ctypes.sizeof(vm._CLedColor), 8)
        self.assertEqual(vm.ctypes.sizeof(vm._CLedPosition), 24)

    def test_devices_with_real_led_positions(self):
        b = vm.CorsairBridge()
        b.dll = FakeICUE()
        with mock.patch.object(vm.CorsairBridge, "dll_path", return_value=Path("x.dll")):
            devs = b.devices(None)
        self.assertEqual(len(devs), 1)
        kb = devs[0]
        self.assertEqual((kb.name, kb.type, len(kb.leds)), ("K70 RGB", 5, 3))
        import vendors
        pos, is_kb = vendors.led_positions(kb)
        self.assertEqual(pos[0], (0.0, 0.0))
        self.assertEqual(pos[2], (1.0, 1.0))
        self.assertTrue(is_kb)
        kb.set_colors([(1, 2, 3), (4, 5, 6), (7, 8, 9)])
        self.assertEqual(b.dll.colors, [(100, 1, 2, 3), (101, 4, 5, 6), (102, 7, 8, 9)])


# ------------------------------------------------------------------ assistente
class TestWizard(unittest.TestCase):
    DEVS = [{"id": 0, "name": "ASRock X570", "type": "MOTHERBOARD", "vendor": "ASRock", "zones": []},
            {"id": 1, "name": "ENE DRAM", "type": "DRAM", "vendor": "ENE", "zones": []},
            {"id": 2, "name": "ENE DRAM", "type": "DRAM", "vendor": "ENE", "zones": []},
            {"id": 3, "name": "PRO Gaming Keyboard", "type": "KEYBOARD", "vendor": "Logitech", "zones": []}]

    def test_auto_profile(self):
        p = rc.auto_profile(self.DEVS, "pt")
        self.assertEqual(p["nicknames"], {"0": "Placa-mãe ASRock", "1": "Memória RAM", "2": "Memória RAM",
                                          "3": "Teclado Logitech"})
        self.assertEqual(p["links"], {"DRAM": "mirror"})
        self.assertIn("Memória RAM (2)", p["summary"])
        self.assertEqual(rc.auto_profile(self.DEVS, "en")["nicknames"]["3"], "Keyboard Logitech")

    def test_run_setup(self):
        with mock.patch.object(rc, "device_info", return_value=self.DEVS), \
             mock.patch.object(rc, "save_pc", side_effect=lambda p: p), \
             mock.patch.object(rc, "apply_claude", return_value=([], {})) as ap, \
             mock.patch.object(rc, "set_autostart", return_value=True) as auto:
            r = rc.run_setup({"colors": ["#FF0000", "#0000FF"], "name": "GTA VI", "autostart": True, "lang": "pt"})
        self.assertTrue(r["autostart"])
        auto.assert_called_once_with(True)
        prof = ap.call_args[0][0]
        self.assertEqual((prof["effect"], prof["links"]), ("static", {"ram": "mirror"}))
        with self.assertRaises(ValueError):
            with mock.patch.object(rc, "device_info", return_value=self.DEVS), \
                 mock.patch.object(rc, "save_pc", side_effect=lambda p: p):
                rc.run_setup({"colors": []})


# ------------------------------------------------------------------ atualização
class TestUpdate(unittest.TestCase):
    def tearDown(self):
        rc._update.update(t=0.0, v=None)

    def fake(self, tag):
        body = json.dumps({"tag_name": tag, "html_url": "https://github.com/x/releases/tag/" + tag,
                           "assets": [{"name": "EasyRGB-windows.zip", "browser_download_url": "https://x/z.zip"}]}).encode()
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = body
        return resp

    def test_newer_version(self):
        with mock.patch("urllib.request.urlopen", return_value=self.fake("v9.0.0")):
            info = rc.check_update(force=True)
        self.assertTrue(info["available"])
        self.assertEqual(info["latest"], "9.0.0")
        self.assertEqual(info["can_install"], rc.FROZEN)

    def test_same_version_and_offline(self):
        with mock.patch("urllib.request.urlopen", return_value=self.fake("v" + rc.VERSION)):
            self.assertFalse(rc.check_update(force=True)["available"])
        with mock.patch("urllib.request.urlopen", side_effect=OSError("sem internet")):
            info = rc.check_update(force=True)
        self.assertFalse(info["available"])
        self.assertIn("error", info)

    def test_versions_compare_as_numbers(self):
        self.assertGreater(rc._ver("1.10.0"), rc._ver("1.9.9"))

    def test_source_install_is_not_replaced(self):
        if rc.FROZEN:
            self.skipTest("só no modo código")
        with mock.patch("urllib.request.urlopen", return_value=self.fake("v9.0.0")):
            with self.assertRaises(RuntimeError):
                rc.install_update()


class TestOwnWindow(unittest.TestCase):
    """A interface abre numa janela própria (Edge em modo app) e não abre duas."""
    def test_opens_app_window_sized_to_screen(self):
        with mock.patch.object(rc, "_focus_window", return_value=False), \
             mock.patch.object(rc, "_edge", return_value=Path(r"C:\Edge\msedge.exe")), \
             mock.patch.object(rc, "_window_size", return_value=(1200, 700)), \
             mock.patch.object(rc.subprocess, "Popen") as po:
            rc.open_ui("http://127.0.0.1:6750/")
        cmd = po.call_args[0][0]
        self.assertIn("--app=http://127.0.0.1:6750/", cmd)
        self.assertIn("--window-size=1200,700", cmd)
        self.assertTrue(any(c.startswith("--user-data-dir=") for c in cmd))   # perfil separado do navegador

    def test_focuses_existing_window(self):
        with mock.patch.object(rc, "_focus_window", return_value=True), mock.patch.object(rc.subprocess, "Popen") as po:
            rc.open_ui()
        po.assert_not_called()

    def test_falls_back_to_default_browser(self):
        with mock.patch.object(rc, "_focus_window", return_value=False), mock.patch.object(rc, "_edge", return_value=None), \
             mock.patch.object(rc.webbrowser, "open") as wb:
            rc.open_ui("http://x/")
        wb.assert_called_once_with("http://x/")

    def test_window_fits_small_screens(self):
        w, h = rc._window_size()
        self.assertTrue(400 <= w <= 1280 and 500 <= h <= 880)


class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.iss = (APP.parent / "installer" / "EasyRGB.iss").read_text(encoding="utf-8")

    def test_clean_text_and_safe_settings(self):
        bad = [ch for ch in self.iss if ord(ch) < 32 and ch not in "\r\n\t"]
        self.assertEqual(bad, [], "caractere de controle no .iss")
        for need in ("PrivilegesRequired=lowest", "ArchitecturesAllowed=x64compatible", "MinVersion=10.0",
                     "{localappdata}\Programs\EasyRGB", "BrazilianPortuguese.isl", "configurado.ok"):
            self.assertIn(need, self.iss)
        # desinstalar nunca apaga os dados do PC (pasta app inteira)
        self.assertNotIn('Type: filesandordirs; Name: "{app}\app"', self.iss)

    def test_update_keeps_data_and_bundled_programs(self):
        src = (APP / "rgb_controller.py").read_text(encoding="utf-8")
        self.assertIn("@('app','OpenRGB','download')", src)


class TestLanguages(unittest.TestCase):
    """Qualquer idioma: a IA cria app/lang/<código>.json e o app usa sozinho."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.p = mock.patch.object(rc, "LANG_DIRS", (self.tmp / "lang", rc.RES / "lang"))
        self.p2 = mock.patch.object(rc, "HERE", self.tmp)
        self.p.start(); self.p2.start()

    def tearDown(self):
        self.p.stop(); self.p2.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_ui_text_is_exported(self):
        src = rc.ui_strings()
        self.assertGreater(len(src), 300)
        self.assertEqual(src["Desconectado"], "Disconnected")

    def test_template_check_and_keep_existing(self):
        f, todo, total = rc.lang_template("es")
        self.assertEqual(todo, total)
        d = json.loads(f.read_text(encoding="utf-8"))
        d["name"] = "Español"
        d["strings"] = {k: "ES " + v for k, v in d["english"].items()}
        k = next(k for k in d["strings"] if "{n}" in k)
        d["strings"][k] = "sin marcador"
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        rep = rc.lang_check("es")
        self.assertEqual(rep["missing"], 0)
        self.assertIn(k, rep["broken_placeholders"])
        _, todo2, _ = rc.lang_template("es")   # rodar de novo mantém o que já foi traduzido
        self.assertEqual(todo2, 0)

    def test_bad_code(self):
        with self.assertRaises(ValueError):
            rc.lang_template("../x")

    def test_page_loads_extra_language(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        self.assertIn('"/lang/"+LANG_CODE+".json"', html)
        self.assertIn('id="langAi"', html)


class TestBackgroundOptimizations(unittest.TestCase):
    def test_process_table_is_fast_and_sees_this_python(self):
        import time
        import vendors
        t0 = time.perf_counter()
        procs = vendors.process_table()
        self.assertLess(time.perf_counter() - t0, 0.5)
        self.assertTrue(any(n.startswith("python") for n in procs))
        self.assertIn(os.getpid(), [p for n, ps in procs.items() if n.startswith("python") for p in ps])

    def test_pc_profile_reread_only_when_file_changes(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            f = tmp / "pc.json"
            with mock.patch.object(rc, "PC_FILE", f):
                self.assertIsNone(rc.load_pc())
                f.write_text('{"a": 1}', encoding="utf-8")
                self.assertEqual(rc.load_pc(), {"a": 1})
                with mock.patch.object(Path, "read_text", side_effect=AssertionError("leu de novo")):
                    self.assertEqual(rc.load_pc(), {"a": 1})   # mesmo arquivo: vem do cache
                import time
                time.sleep(0.02)
                f.write_text('{"a": 22}', encoding="utf-8")
                self.assertEqual(rc.load_pc(), {"a": 22})
                rc.load_pc()["a"] = 99                          # quem chama não estraga o cache
                self.assertEqual(rc.load_pc(), {"a": 22})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestGamesAndHotkeys(unittest.TestCase):
    def test_picks_the_real_game_exe(self):
        import games
        tmp = Path(tempfile.mkdtemp())
        try:
            g = tmp / "Palworld"
            (g / "Pal" / "Binaries" / "Win64").mkdir(parents=True)
            (g / "Pal" / "Binaries" / "Win64" / "Palworld-Win64-Shipping.exe").write_bytes(b"x" * 5000)
            (g / "Palworld.exe").write_bytes(b"x" * 100)                      # launcher pequeno
            (g / "UnrealCEFSubProcess.exe").write_bytes(b"x" * 9000)
            (g / "unins000.exe").write_bytes(b"x" * 9000)
            (g / "Engine" / "Extras" / "Redist").mkdir(parents=True)
            (g / "Engine" / "Extras" / "Redist" / "UEPrereqSetup_x64.exe").write_bytes(b"x" * 90000)
            self.assertEqual(games.pick_exe(g, "Palworld").name, "Palworld-Win64-Shipping.exe")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_steam_manifests_and_non_games(self):
        import games
        tmp = Path(tempfile.mkdtemp())
        try:
            apps = tmp / "steamapps"
            for i, (name, inst, exe) in enumerate([("Counter-Strike 2", "Counter-Strike Global Offensive", "cs2.exe"),
                                                   ("Wallpaper Engine", "wallpaper_engine", "wallpaper64.exe"),
                                                   ("Steamworks Common Redistributables", "Steamworks Shared", "x.exe")]):
                (apps / "common" / inst).mkdir(parents=True)
                (apps / "common" / inst / exe).write_bytes(b"x" * 1000)
                (apps / f"appmanifest_{i}.acf").write_text(f'"AppState"\n{{\n "name" "{name}"\n "installdir" "{inst}"\n}}', encoding="utf-8")
            with mock.patch.dict(os.environ, {"ProgramFiles(x86)": str(tmp.parent)}), \
                 mock.patch.object(games, "steam_games", lambda: ((n, f, s) for n, f, s in
                                   [(n, apps / "common" / i, "Steam") for n, i in
                                    [("Counter-Strike 2", "Counter-Strike Global Offensive")]])), \
                 mock.patch.object(games, "epic_games", lambda: iter(())), \
                 mock.patch.object(games, "registry_games", lambda: iter(())), \
                 mock.patch.object(games, "folder_games", lambda: iter(())):
                found = games.find_games({"cs2.exe": "Fogo"}, force=True)
            self.assertEqual([(g["name"], g["process"], g["preset"]) for g in found], [("Counter-Strike 2", "cs2.exe", "Fogo")])
            self.assertTrue(games._NOT_GAMES.search("Wallpaper Engine"))
            self.assertTrue(games._NOT_GAMES.search("Steamworks Common Redistributables"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            import games as g2
            g2._cache.update(t=0.0, v=None)

    def test_hotkey_parsing(self):
        self.assertEqual(rc.parse_hotkey("Ctrl+Alt+Right"), (0x0002 | 0x0001, 0x27))
        self.assertEqual(rc.parse_hotkey("Ctrl+Shift+F1"), (0x0002 | 0x0004, 0x70))
        self.assertIsNone(rc.parse_hotkey("A"))            # sem modificador rouba a tecla
        self.assertIsNotNone(rc.parse_hotkey("F13"))      # F13-F24 podem ficar sozinhas
        self.assertIsNone(rc.parse_hotkey("Ctrl+Banana"))
        m = rc.clean_hotkeys({"next": "Ctrl+K", "prev": "lixo", "toggle": ""})
        self.assertEqual((m["next"], m["prev"], m["toggle"]), ("Ctrl+K", "Ctrl+Alt+Left", ""))

    def test_saved_rules_keep_game_name_and_shortcuts(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            with mock.patch.object(rc, "AUTO_FILE", tmp / "a.json"):
                a = rc.save_auto({"games": [{"process": "cs2.exe", "preset": "Fogo", "name": "Counter-Strike 2"}],
                                  "hotkeys": True, "hotkey_map": {"next": "Ctrl+Shift+N"}})
                self.assertEqual(a["games"][0]["name"], "Counter-Strike 2")
                self.assertEqual(rc.load_auto()["hotkey_map"]["next"], "Ctrl+Shift+N")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestPerDeviceBrightness(unittest.TestCase):
    @unittest.skipUnless(getattr(rc, "FROZEN", False) is False, "modo código")
    def test_device_brightness_scales_only_that_device(self):
        try:
            from openrgb.utils import RGBColor  # noqa: F401
        except ImportError:
            self.skipTest("bibliotecas ainda não instaladas")
        from test_core import FakeClient, FakeDev, FakeMode, FakeZone
        a = FakeDev("Board", 0, [FakeZone("Z", 2)], [FakeMode("Direct", 32, 1)])
        b = FakeDev("Kb", 5, [FakeZone("K", 2)], [FakeMode("Direct", 32, 1)])
        with mock.patch.dict(os.environ, {"EASYRGB_NO_VENDORS": "1"}),              mock.patch.object(rc, "client", return_value=FakeClient([a, b])):
            rc.apply([(200, 100, 0)], 100, persist=False, dev_bri={"1": 50})
        cols = lambda d: [c for c in d.calls if c[0] == "colors"][-1][1]   # noqa: E731
        self.assertEqual(cols(a)[0], (200, 100, 0))
        self.assertEqual(cols(b)[0], (100, 50, 0))


class TestUiHasNewParts(unittest.TestCase):
    def test_wizard_functions_exist(self):
        """Toda função chamada pelo assistente precisa existir (uma faltando deixava o assistente sem abrir)."""
        import re
        html = (APP / "index.html").read_text(encoding="utf-8")
        js = html[html.index("<script>"):]
        for name in ("wizStep", "wizDevices", "openWizard", "missingPrompt", "maybeWizard"):
            self.assertIn(f"function {name}(", js)
        body = js[js.index("function openWizard("):js.index("function missingPrompt(")]
        for call in set(re.findall(r"(wiz[A-Z]\w*)\(", body)):
            self.assertIn(f"function {call}(", js, call)

    def test_ids_and_translations(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        for i in ("wiz", "wizDevs", "wizRescan", "wizAsk", "wizAuto", "wizDone", "wizSkip", "updPill"):
            self.assertIn(f'id="{i}"', html)
        for s in ("Bem-vindo ao EasyRGB", "Procurar com IA", "Procurar de novo", "Atualizar para {v}"):
            self.assertIn(f'"{s}":', html)


if __name__ == "__main__":
    unittest.main()
