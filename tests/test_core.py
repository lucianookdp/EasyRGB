"""Testes do EasyRGB sem hardware: hardware simulado, lógica de cores, automação, API e interface.

Rodar:  python -m unittest discover -s tests -v
"""
import json
import os
import re
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

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(APP))

os.environ["EASYRGB_NO_VENDORS"] = "1"   # testes nao mexem no G HUB de verdade
import rgb_controller as rc  # noqa: E402

try:
    from openrgb.utils import RGBColor  # noqa: F401  (instalada pelo instalador em app/lib)
    HAS_LIB = True
except ImportError:
    HAS_LIB = False


# ------------------------------------------------------------------ hardware simulado
class FakeMode:
    def __init__(self, name, flags=0, color_mode=0, speed_min=None, speed_max=None, colors_min=None, colors_max=None):
        self.name, self.flags, self.color_mode = name, flags, color_mode
        self.speed_min, self.speed_max, self.speed = speed_min, speed_max, None
        self.colors_min, self.colors_max, self.colors = colors_min, colors_max, []


class FakeZone:
    def __init__(self, name, n):
        self.name, self.leds = name, [0] * n


class FakeDev:
    def __init__(self, name, typ, zones, modes):
        self.name, self.type, self.zones, self.modes = name, typ, zones, modes
        self.active_mode, self.calls = 0, []

    def set_mode(self, m, save=False):
        name = m if isinstance(m, str) else m.name
        self.active_mode = next(i for i, x in enumerate(self.modes) if x.name.lower() == name.lower())
        name = self.modes[self.active_mode].name
        self.calls.append(("mode", name, getattr(m, "speed", None), len(getattr(m, "colors", []) or []), save))

    def set_colors(self, cols, fast=False):
        self.calls.append(("colors", [(c.red, c.green, c.blue) for c in cols], fast))

    def save_mode(self):
        self.calls.append(("save",))

    def off(self):
        self.calls.append(("off",))


class FakeClient:
    def __init__(self, devices):
        self.devices = devices

    def update(self):
        pass


def fake_pc():
    """Parecido com o PC real: placa ASRock (só Static), 2 RAMs ENE (Direct) e um teclado."""
    board = FakeDev("ASRock X570", 0, [FakeZone(n, 1) for n in ("RGB 1", "RGB 2", "PCH", "IO Cover", "Audio", "ARGB")], [
        FakeMode("Off"), FakeMode("Static", 544, 1), FakeMode("Breathing", 545, 1, 10, 2),
        FakeMode("Rainbow", 513, 0, 18, 1), FakeMode("Music", 512), FakeMode("ARGB Header Config", 515)])
    ram = lambda: FakeDev("ENE DRAM", 1, [FakeZone("DRAM", 8)], [  # noqa: E731
        FakeMode("Direct", 32, 1), FakeMode("Off"), FakeMode("Static", 32, 1),
        FakeMode("Chase", 163, 1, 4, 0), FakeMode("Spectrum Cycle", 1, 0, 4, 0)])
    kb = FakeDev("PRO Gaming Keyboard", 5, [FakeZone("Keyboard", 92), FakeZone("Extras", 2)], [
        FakeMode("Direct", 32, 1), FakeMode("Static", 320, 2, colors_min=1, colors_max=1),
        FakeMode("Breathing", 321, 2, 1, 100, 1, 1), FakeMode("Color Wave", 257, 0, 1, 100)])
    return [board, ram(), ram(), kb]


HEX = lambda s: rc.parse_colors(s)  # noqa: E731


class TempFiles(unittest.TestCase):
    """Isola os arquivos de estado do app numa pasta temporária."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(APP / "palettes.json", self.tmp / "palettes.json")
        self.patches = [mock.patch.object(rc, n, self.tmp / f) for n, f in (
            ("STATE_FILE", "last_state.json"), ("PALETTES_FILE", "palettes.json"), ("CLAUDE_FILE", "claude.json"),
            ("PC_FILE", "pc.json"), ("AUTO_FILE", "automations.json"), ("USER_PRESETS_FILE", "my_presets.json"))]
        for p in self.patches:
            p.start()
        rc._hw_cache.clear()

    def tearDown(self):
        rc.stop_effect()
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


# ------------------------------------------------------------------ cores
class TestColors(unittest.TestCase):
    def test_parse_formats(self):
        got = rc.parse_colors("#FF2E88, 9b3dff; rgb(0,217,200) #fff abc #12345")
        self.assertEqual([rc.to_hex(c) for c in got], ["#FF2E88", "#9B3DFF", "#00D9C8", "#FFFFFF"])

    def test_parse_list_and_clamp(self):
        self.assertEqual(rc.parse_colors(["#000000", "rgb(300, 10, 10)"]), [(0, 0, 0), (255, 10, 10)])
        self.assertEqual(rc.parse_colors(None), [])

    def test_gradient_endpoints_and_sizes(self):
        g = rc.gradient(HEX("#FF0000 #0000FF"), 5)
        self.assertEqual(g[0], (255, 0, 0))
        self.assertEqual(g[-1], (0, 0, 255))
        self.assertEqual(len(rc.gradient(HEX("#FF0000 #00FF00 #0000FF"), 94)), 94)
        self.assertEqual(rc.gradient(HEX("#123456"), 3), [(0x12, 0x34, 0x56)] * 3)
        self.assertEqual(rc.gradient(HEX("#FF0000 #0000FF"), 0), [])
        self.assertEqual(rc.gradient(HEX("#FF0000 #0000FF"), 1), [(255, 0, 0)])

    def test_gradient_offset_is_circular(self):
        pal = HEX("#FF0000 #0000FF")
        a, b = rc.gradient(pal, 8, 0.25), rc.gradient(pal, 8, 0.75)
        self.assertEqual(len(a), 8)
        self.assertNotEqual(a, b)

    def test_scale(self):
        self.assertEqual(rc.scale((200, 100, 50), 50), (100, 50, 25))
        self.assertEqual(rc.scale((200, 100, 50), 150), (200, 100, 50))

    def test_zone_modes(self):
        pal = HEX("#FF0000 #00FF00 #0000FF")
        self.assertEqual(rc.zone_colors(3, 4, pal, "zona"), [pal[1]] * 3)
        self.assertEqual(rc.zone_colors(4, 0, pal, "alternado"), [pal[0], pal[1], pal[2], pal[0]])
        self.assertEqual(rc.zone_colors(1, 2, pal, "gradiente"), [pal[2]])  # zona de 1 LED usa uma cor por zona


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.devs = fake_pc()
        self.pal = HEX("#FF0000 #0000FF")

    def test_separate_each_device_full_gradient(self):
        p = rc.plan_colors(self.devs, [0, 1, 2, 3], self.pal, "gradiente", 0, {}, [])
        self.assertEqual(p[1], p[2])
        self.assertEqual(p[1][0], (255, 0, 0))
        self.assertEqual(p[1][-1], (0, 0, 255))
        self.assertEqual(len(p[3]), 94)

    def test_span_crosses_modules(self):
        p = rc.plan_colors(self.devs, [0, 1, 2, 3], self.pal, "gradiente", 0, {}, [{"ids": [1, 2], "mode": "span"}])
        self.assertEqual(p[1][0], (255, 0, 0))
        self.assertEqual(p[2][-1], (0, 0, 255))
        self.assertNotEqual(p[1][-1], (0, 0, 255))  # o 1º módulo não termina no azul

    def test_mirror_copies_lead_overrides(self):
        p = rc.plan_colors(self.devs, [0, 1, 2, 3], self.pal, "gradiente", 0, {"1": {"0": "#00FF00"}, "2": {"0": "#FFFFFF"}},
                           [{"ids": [1, 2], "mode": "mirror"}])
        self.assertEqual(p[1], [(0, 255, 0)] * 8)
        self.assertEqual(p[2], [(0, 255, 0)] * 8)

    def test_overrides_and_excluded(self):
        p = rc.plan_colors(self.devs, [0, 3], self.pal, "gradiente", 0, {"0": {"3": "#FFFFFF"}}, [])
        self.assertNotIn(1, p)
        self.assertEqual(p[0][3], (255, 255, 255))

    def test_per_key_override(self):
        p = rc.plan_colors(self.devs, [3], self.pal, "gradiente", 0, {"3": {"L5": "#00FF00", "L999": "#FFFFFF"}}, [])
        self.assertEqual(p[3][5], (0, 255, 0))
        self.assertEqual(len(p[3]), 94)   # índice fora do teclado é ignorado

    def test_group_with_one_enabled_member_is_ignored(self):
        p = rc.plan_colors(self.devs, [1], self.pal, "gradiente", 0, {}, [{"ids": [1, 2], "mode": "span"}])
        self.assertEqual(p[1][-1], (0, 0, 255))


# ------------------------------------------------------------------ hardware
@unittest.skipUnless(HAS_LIB, "biblioteca openrgb-python não instalada (rode o instalador)")
class TestHardware(TempFiles):
    def test_hw_effects_filters_and_classifies(self):
        fx = {e["name"]: e for e in rc.hw_effects(fake_pc()[0])}
        self.assertNotIn("Static", fx)
        self.assertNotIn("Music", fx)
        self.assertNotIn("ARGB Header Config", fx)
        self.assertEqual(fx["Breathing"]["colors"], "led")
        self.assertEqual(fx["Rainbow"]["colors"], "none")
        self.assertTrue(fx["Breathing"]["speed"])
        kb = {e["name"]: e for e in rc.hw_effects(fake_pc()[3])}
        self.assertEqual(kb["Breathing"]["colors"], "mode")

    def test_apply_hw_speed_inverted_range_and_cache(self):
        from openrgb.utils import RGBColor
        dev = fake_pc()[0]
        rc.apply_hw(0, dev, "breathing", 100, [(1, 2, 3)] * 6, [(255, 0, 0)], False, RGBColor)
        self.assertEqual(dev.calls[0][:3], ("mode", "Breathing", 2))  # 100% = valor mais rápido (2)
        self.assertEqual(dev.calls[1][0], "colors")
        rc.apply_hw(0, dev, "Breathing", 100, [(9, 9, 9)] * 6, [(255, 0, 0)], False, RGBColor)
        self.assertEqual([c[0] for c in dev.calls], ["mode", "colors", "colors"])  # não reenviou o modo

    def test_apply_hw_mode_specific_colors(self):
        from openrgb.utils import RGBColor
        kb = fake_pc()[3]
        rc.apply_hw(3, kb, "Breathing", 0, [], HEX("#FF0000 #00FF00 #0000FF"), False, RGBColor)
        self.assertEqual(kb.calls[0][3], 1)  # teclado aceita 1 cor nesse modo
        with self.assertRaises(ValueError):
            rc.apply_hw(3, kb, "Inexistente", 0, [], [(1, 1, 1)], False, RGBColor)

    def test_apply_writes_brightness_and_state(self):
        devs = fake_pc()
        with mock.patch.object(rc, "client", return_value=FakeClient(devs)):
            rep = rc.apply(HEX("#FF0000"), 50, "gradiente", None, persist=True)
        self.assertTrue(all(r["ok"] for r in rep))
        self.assertEqual(devs[0].calls[0][:2], ("mode", "Static"))  # placa estava em Off: vai para Static
        self.assertEqual(devs[1].calls[0][0], "colors")             # RAM já estava em Direct: só manda cores
        self.assertEqual(devs[1].calls[-1][1][0], (128, 0, 0))
        st = json.loads(rc.STATE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(st["brightness"], 50)

    def test_preview_does_not_persist(self):
        with mock.patch.object(rc, "client", return_value=FakeClient(fake_pc())):
            rc.apply(HEX("#FF0000"), 100, persist=False)
        self.assertFalse(rc.STATE_FILE.exists())

    def test_apply_hw_device_and_back_to_direct(self):
        devs = fake_pc()
        with mock.patch.object(rc, "client", return_value=FakeClient(devs)):
            rc.apply(HEX("#FF0000"), 100, hw={"1": {"mode": "Chase", "speed": 50}}, persist=False)
            self.assertEqual(devs[1].modes[devs[1].active_mode].name, "Chase")
            rc.apply(HEX("#FF0000"), 100, persist=False)
            self.assertEqual(devs[1].modes[devs[1].active_mode].name, "Direct")

    def test_apply_empty_palette_raises(self):
        with self.assertRaises(ValueError):
            rc.apply([], 100)

    def test_resolve_profile(self):
        devs = fake_pc()
        p = {"zones": [{"device": "teclado", "color": "#FFFFFF"}, {"device": "placa", "zone": "io", "color": "#FF0000"}],
             "links": {"ram": "continuas"}, "hw": [{"device": "ram", "mode": "chase", "speed": 70}],
             "exclude": ["mouse"]}
        ids, ov, groups, links, hw = rc.resolve_profile(p, devs)
        self.assertEqual(ids, [0, 1, 2, 3])
        self.assertEqual(ov["3"], {"0": "#FFFFFF", "1": "#FFFFFF"})
        self.assertEqual(ov["0"], {"3": "#FF0000"})
        self.assertEqual(groups, [{"ids": [1, 2], "mode": "span"}])
        self.assertEqual(links, {"DRAM": "span"})
        self.assertEqual(hw["1"], {"mode": "Chase", "speed": 70})
        ids, *_ = rc.resolve_profile({"exclude": ["teclado"]}, devs)
        self.assertEqual(ids, [0, 1, 2])

    def test_match_zones(self):
        zones = fake_pc()[0].zones  # RGB 1, RGB 2, PCH, IO Cover, Audio, ARGB
        self.assertEqual(rc._match_zones("io", zones), [3])
        self.assertEqual(rc._match_zones("audio", zones), [4])
        self.assertEqual(rc._match_zones("rgb", zones), [0, 1])
        self.assertEqual(rc._match_zones("gb", zones), [0, 1, 5])
        self.assertEqual(rc._match_zones("", zones), [0, 1, 2, 3, 4, 5])
        self.assertEqual(rc._match_zones("9", zones), [])

    def test_apply_claude_saves_history(self):
        with mock.patch.object(rc, "client", return_value=FakeClient(fake_pc())):
            rc.apply_claude({"name": "A", "colors": ["#FF0000"]}, allow_effect=False)
            rc.apply_claude({"name": "B", "colors": ["#00FF00"]}, allow_effect=False)
            rc.apply_claude({"name": "A", "colors": ["#0000FF"]}, allow_effect=False)
        c = rc.load_claude()
        self.assertEqual(c["active"]["name"], "A")
        self.assertEqual([h["name"] for h in c["history"]], ["A", "B"])
        with self.assertRaises(ValueError):
            rc.apply_claude({"name": "sem cor", "colors": []})

    def test_apply_saved_restores_with_changes(self):
        devs = fake_pc()
        with mock.patch.object(rc, "client", return_value=FakeClient(devs)):
            rc.apply(HEX("#FF0000"), 100, persist=True)
            devs[1].calls.clear()
            rc.apply_saved(brightness=10)
        self.assertEqual(devs[1].calls[-1][1][0], (26, 0, 0))
        self.assertEqual(json.loads(rc.STATE_FILE.read_text(encoding="utf-8"))["brightness"], 100)  # não salvou


# ------------------------------------------------------------------ efeitos animados
class TestEffects(unittest.TestCase):
    def test_frames(self):
        pal = HEX("#FF0000 #0000FF")
        for t in (0, 0.3, 1.7):
            p, b, off = rc._frame("respirar", pal, 100, t, 5)
            self.assertTrue(7 <= b <= 100)
            self.assertEqual(p, pal)
        p, b, off = rc._frame("ciclo", pal, 80, 1.0, 5)
        self.assertEqual(len(p), 1)
        self.assertEqual(b, 80)
        p, _, off = rc._frame("arcoiris", pal, 100, 0.5, 5)
        self.assertEqual(p, rc.RAINBOW)
        self.assertTrue(0 < off <= 1)
        _, _, off = rc._frame("fluir", pal, 100, 0, 5)
        self.assertGreater(off, 0)  # offset nunca é 0 (0 desligaria o modo circular)


# ------------------------------------------------------------------ automação
class TestAutomation(TempFiles):
    def test_game_rule(self):
        a = {"games": [{"process": "VALORANT-Win64-Shipping.exe", "preset": "Valorant"},
                       {"process": "cs2.exe", "preset": "Counter-Strike 2", "enabled": False}]}
        self.assertEqual(rc.game_rule(a, {"valorant-win64-shipping.exe"})["preset"], "Valorant")
        self.assertIsNone(rc.game_rule(a, {"cs2.exe"}))
        self.assertIsNone(rc.game_rule(dict(a, enabled=False), {"valorant-win64-shipping.exe"}))

    def test_due_schedules_once_per_day(self):
        a = {"schedule": [{"time": "23:00", "action": "off"}, {"time": "08:00", "action": "restore", "enabled": False}]}
        fired = {}
        self.assertEqual(len(rc.due_schedules(a, "23:00", "2026-11-18", fired)), 1)
        self.assertEqual(rc.due_schedules(a, "23:00", "2026-11-18", fired), [])
        self.assertEqual(len(rc.due_schedules(a, "23:00", "2026-11-19", fired)), 1)
        self.assertEqual(rc.due_schedules(a, "08:00", "2026-11-19", fired), [])

    def test_save_auto_sanitizes(self):
        a = rc.save_auto({"games": [{"process": " cs2.exe ", "preset": "Counter-Strike 2"}, {"preset": "sem exe"}],
                          "schedule": [{"time": "23:00", "action": "brightness", "value": 20}, {"time": "25h"}]})
        self.assertEqual(a["games"], [{"process": "cs2.exe", "preset": "Counter-Strike 2", "enabled": True}])
        self.assertEqual(len(a["schedule"]), 1)
        self.assertEqual(rc.load_auto()["games"][0]["process"], "cs2.exe")

    def test_known_games_have_presets(self):
        names = set(rc.load_palettes())
        for exe, preset in rc.KNOWN_GAMES.items():
            self.assertTrue(exe.lower().endswith(".exe"), exe)
            self.assertIn(preset, names, f"{exe} aponta para um preset que não existe")

    @unittest.skipUnless(HAS_LIB, "precisa da biblioteca openrgb-python")
    def test_tick_switches_to_game_and_back(self):
        devs = fake_pc()
        rc.save_auto({"games": [{"process": "cs2.exe", "preset": "Valorant"}]})
        with mock.patch.object(rc, "client", return_value=FakeClient(devs)), \
                mock.patch.object(rc, "openrgb_running", return_value=True):
            rc.apply(HEX("#123456"), 100, persist=True)
            with mock.patch.object(rc, "running_processes", return_value={"cs2.exe"}):
                rc.auto_tick()
            self.assertEqual(rc._auto["game"]["process"], "cs2.exe")
            self.assertEqual(devs[1].calls[-1][1][0], (0xFF, 0x46, 0x55))  # 1ª cor do preset Valorant
            with mock.patch.object(rc, "running_processes", return_value=set()):
                rc.auto_tick()
            self.assertIsNone(rc._auto["game"])
            self.assertEqual(devs[1].calls[-1][1][0], (0x12, 0x34, 0x56))  # voltou ao visual do usuário

    def test_persist_kind(self):
        board, ram, _, kb = fake_pc()
        self.assertEqual(rc.persist_kind(board), "auto")    # Static com salvamento automático
        self.assertEqual(rc.persist_kind(ram), "none")      # RAM ENE não guarda
        self.assertEqual(rc.persist_kind(kb), "manual")     # teclado guarda uma cor fixa

    def test_needs_running(self):
        self.assertFalse(rc.needs_running())
        rc.save_auto({"schedule": [{"time": "23:00", "action": "off"}]})
        self.assertTrue(rc.needs_running())
        rc.save_auto({"enabled": False, "schedule": [{"time": "23:00", "action": "off"}]})
        self.assertFalse(rc.needs_running())
        rc.STATE_FILE.write_text(json.dumps({"palette": ["#FF0000"], "ui": {"effect": "fluir"}}), encoding="utf-8")
        self.assertTrue(rc.needs_running())

    @unittest.skipUnless(HAS_LIB, "precisa da biblioteca openrgb-python")
    def test_boot_restores_then_exits_when_idle(self):
        devs = fake_pc()
        rc.STATE_FILE.write_text(json.dumps({"palette": ["#00FF00"], "brightness": 100, "ui": {}}), encoding="utf-8")
        with mock.patch.object(rc, "client", return_value=FakeClient(devs)), \
                mock.patch.object(rc, "openrgb_running", return_value=False), \
                mock.patch.object(rc, "start_openrgb", return_value=True), \
                mock.patch.object(rc.subprocess, "run") as run, \
                mock.patch.object(rc.os, "_exit", side_effect=SystemExit) as ex, \
                mock.patch.object(rc.time, "sleep"):
            with self.assertRaises(SystemExit):
                rc.restore_on_boot()
        self.assertEqual(devs[1].calls[-1][1][0], (0, 255, 0))           # devolveu a cor
        self.assertIn("OpenRGB.exe", run.call_args[0][0])                 # fechou o OpenRGB que ele abriu
        ex.assert_called_once_with(0)                                     # e saiu: nada fica na memória

    @unittest.skipUnless(HAS_LIB, "precisa da biblioteca openrgb-python")
    def test_boot_stays_when_automation(self):
        rc.STATE_FILE.write_text(json.dumps({"palette": ["#00FF00"], "ui": {}}), encoding="utf-8")
        rc.save_auto({"games": [{"process": "cs2.exe", "preset": "Counter-Strike 2"}]})
        with mock.patch.object(rc, "client", return_value=FakeClient(fake_pc())), \
                mock.patch.object(rc, "start_openrgb", return_value=True), \
                mock.patch.object(rc.os, "_exit") as ex:
            rc.restore_on_boot()
        ex.assert_not_called()

    def test_running_processes_real(self):
        procs = rc.running_processes()
        self.assertIn(Path(sys.executable).name.lower(), procs)  # o próprio Python que roda o teste
        self.assertTrue(all(p == p.lower() for p in procs))


class TestMcpServer(unittest.TestCase):
    """Servidor MCP: apps de IA (Claude Desktop, Cursor...) controlam as luzes pelo chat."""
    def setUp(self):
        import mcp_server
        self.m = mcp_server
        self.sent = []
        st = {"connected": True, "palettes": {"GTA VI": ["#F1047A", "#BB08F7"], "Synthwave": ["#FF2BD6", "#00E1FF"]},
              "devices": [{"id": 0, "name": "Board", "type": "MOTHERBOARD", "zones": [{"name": "A", "leds": 6}]},
                          {"id": 3, "name": "PRO Gaming Keyboard", "type": "KEYBOARD", "zones": [{"name": "K", "leds": 94}]}],
              "last": {"palette": ["#111111", "#222222"], "brightness": 80, "mode": "gradiente",
                       "ui": {"effect": "static", "pfx": {"3": "onda"}, "speed": 3, "links": {"DRAM": "mirror"}}},
              "pc": {"nicknames": {"3": "Teclado"}}}

        def fake(path, body=None, timeout=60):
            self.sent.append((path, body))
            return st if path == "/api/state" else {"ok": True, "report": [{"device": "Board", "ok": True}]}
        self.p = [mock.patch.object(mcp_server, "_call", side_effect=fake),
                  mock.patch.object(mcp_server, "ensure_app")]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def rpc(self, method, params=None, mid=1):
        return self.m.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})

    def test_handshake_and_tools(self):
        r = self.rpc("initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(r["serverInfo"]["name"], "easyrgb")
        self.assertIn("tools", r["capabilities"])
        self.assertIsNone(self.m.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        names = [t["name"] for t in self.rpc("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["easyrgb_status", "easyrgb_apply_look", "easyrgb_brightness", "easyrgb_lights"])
        self.assertIn("error", self.rpc("nada/aqui"))

    def test_status_uses_nicknames(self):
        r = self.rpc("tools/call", {"name": "easyrgb_status", "arguments": {}})["result"]
        out = json.loads(r["content"][0]["text"])
        self.assertFalse(r["isError"])
        self.assertEqual(out["devices"][1]["name"], "Teclado")
        self.assertIn("GTA VI", out["presets"])

    def test_apply_preset_keeps_keyboard_effect(self):
        r = self.rpc("tools/call", {"name": "easyrgb_apply_look", "arguments": {"preset": "synthwave"}})["result"]
        self.assertFalse(r["isError"], r)
        path, prof = self.sent[-1]
        self.assertEqual(path, "/api/claude")
        self.assertEqual(prof["colors"], ["#FF2BD6", "#00E1FF"])
        self.assertEqual(prof["brightness"], 80)
        self.assertEqual(prof["peripheral_effects"], {"PRO Gaming Keyboard": "onda"})

    def test_errors_are_reported_to_the_ai(self):
        r = self.rpc("tools/call", {"name": "easyrgb_apply_look", "arguments": {"preset": "nao existe"}})["result"]
        self.assertTrue(r["isError"])
        self.assertIn("Preset not found", r["content"][0]["text"])

    def test_install_into_claude_desktop_keeps_other_servers(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            roaming, local = tmp / "Roaming", tmp / "Local"
            store = local / "Packages" / "Claude_abc" / "LocalCache" / "Roaming" / "Claude"
            store.mkdir(parents=True)
            (roaming / "Claude").mkdir(parents=True)
            (roaming / "Claude" / "claude_desktop_config.json").write_text(
                json.dumps({"mcpServers": {"outro": {"command": "x"}}, "theme": "dark"}), encoding="utf-8")
            with mock.patch.dict(os.environ, {"APPDATA": str(roaming), "LOCALAPPDATA": str(local)}):
                files = self.m.install_claude_desktop()
            self.assertEqual(len(files), 2)   # instalador normal + versão da Microsoft Store
            a = json.loads((roaming / "Claude" / "claude_desktop_config.json").read_text(encoding="utf-8"))
            self.assertEqual(set(a["mcpServers"]), {"outro", "easyrgb"})
            self.assertEqual(a["theme"], "dark")
            b = json.loads((store / "claude_desktop_config.json").read_text(encoding="utf-8"))
            self.assertIn("--mcp" if self.m.FROZEN else "mcp_server.py", json.dumps(b["mcpServers"]["easyrgb"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_stdio_loop(self):
        import io
        inp = io.StringIO('{"jsonrpc":"2.0","id":7,"method":"ping"}' + "\n" + "not json" + "\n")
        out = io.StringIO()
        self.m.serve(inp, out)
        lines = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(lines[0], {"jsonrpc": "2.0", "id": 7, "result": {}})
        self.assertEqual(lines[1]["error"]["code"], -32700)


class TestStartupTask(unittest.TestCase):
    """O "Restaurar ao ligar o PC" não pode quebrar quando o Python do PC muda de versão."""
    def test_broken_task_counts_as_off(self):
        with mock.patch.object(rc, "autostart_task_command", return_value=r"C:\Nao\Existe\pythonw.exe"):
            self.assertFalse(rc.autostart_installed(fresh=True))
        with mock.patch.object(rc, "autostart_task_command", return_value=None):
            self.assertFalse(rc.autostart_installed(fresh=True))
        with mock.patch.object(rc, "autostart_task_command", return_value=sys.executable):
            self.assertTrue(rc.autostart_installed(fresh=True))

    def test_launcher_does_not_pin_a_python_version(self):
        exe = rc.launcher()
        self.assertTrue(exe.exists())
        if (Path(os.environ.get("WINDIR", r"C:\Windows")) / "pyw.exe").exists():
            self.assertEqual(exe.name.lower(), "pyw.exe")

    def test_libraries_are_per_python_version(self):
        self.assertEqual(rc.LIB.name, f"py{sys.version_info[0]}{sys.version_info[1]}")
        self.assertIn("pillow", rc.REQUIREMENTS)


# ------------------------------------------------------------------ compartilhar
class TestOldFiles(TempFiles):
    def test_old_automation_file_with_temperature_extras(self):
        rc.AUTO_FILE.write_text(json.dumps({"enabled": True, "games": [], "schedule": [], "hotkeys": False,
                                            "extras": {"temp_source": "gpu", "temp_min": 40, "temp_max": 80}}),
                                encoding="utf-8")
        a = rc.load_auto()
        self.assertNotIn("extras", a)


class TestShare(unittest.TestCase):
    def test_roundtrip(self):
        code = rc.share_code({"palette": ["#FF2E88", "#00D9C8"], "mode": "zona", "brightness": 70, "name": "Praia",
                              "ui": {"effect": "respirar", "speed": 6, "links": {"DRAM": "span"}}})
        self.assertTrue(code.startswith("EASYRGB1-"))
        look = rc.read_share_code(code)
        self.assertEqual(look["colors"], ["#FF2E88", "#00D9C8"])
        self.assertEqual((look["mode"], look["brightness"], look["effect"], look["name"]), ("zona", 70, "respirar", "Praia"))
        self.assertEqual(look["links"], {"DRAM": "span"})

    def test_old_prefix_still_works(self):
        code = rc.share_code({"palette": ["#123456"], "name": "Velho"})
        old = "MEURGB1-" + code.split("-", 1)[1]
        self.assertEqual(rc.read_share_code(old)["colors"], ["#123456"])

    def test_invalid_codes(self):
        for bad in ("", "abc", "EASYRGB1-!!!", rc.share_code({"palette": []})):
            with self.assertRaises(Exception):
                rc.read_share_code(bad)


# ------------------------------------------------------------------ presets
class TestPresets(unittest.TestCase):
    def test_palettes_file(self):
        pal = json.loads((APP / "palettes.json").read_text(encoding="utf-8"))
        self.assertTrue(10 <= len(pal) <= 16, "lista enxuta: entre 10 e 16 presets")
        for name, cols in pal.items():
            self.assertTrue(cols, name)
            for c in cols:
                self.assertRegex(c, r"^#[0-9A-F]{6}$", f"{name}: {c}")
                self.assertGreaterEqual(max(rc.parse_colors(c)[0]), 0x80, f"{name}: {c} escura demais para LED")
        for keep in ("GTA VI", "Branco Frio", "Matrix", "Fogo", "Oceano",
                     "Roxo Profundo", "Synthwave", "Valorant", "Cyberpunk 2077", "Portal"):
            self.assertIn(keep, pal)
        for gone in ("Trabalho (suave)", "GTA VI - Praia Dourada", "GTA VI - Vice City Sunset", "GTA VI - Neon Leonida", "Super Mario", "Pac-Man", "Halo", "DOOM"):
            self.assertNotIn(gone, pal)

    def test_find_preset(self):
        self.assertEqual(rc.find_preset("synth")[0], "Synthwave")
        self.assertEqual(rc.find_preset("por do sol")[0], "Pôr do Sol")
        self.assertEqual(rc.find_preset("zzz"), (None, None))


class TestUserPresets(TempFiles):
    def test_user_presets_are_separate(self):
        builtin = dict(rc.builtin_presets())
        rc.save_user_preset("Meu Neon", ["#FF00AA", "00FFEE"])
        self.assertEqual(rc.user_presets(), {"Meu Neon": ["#FF00AA", "#00FFEE"]})
        self.assertEqual(rc.builtin_presets(), builtin)                    # padrão nunca muda
        self.assertEqual(list(rc.load_palettes())[0], "Meu Neon")          # os do usuário vêm primeiro
        with self.assertRaises(ValueError):
            rc.save_user_preset("Fogo", ["#FF0000"])                         # nome de preset padrão
        with self.assertRaises(ValueError):
            rc.delete_user_preset("Fogo")                                    # padrão não apaga
        rc.delete_user_preset("Meu Neon")
        self.assertEqual(rc.user_presets(), {})


# ------------------------------------------------------------------ servidor HTTP
@unittest.skipUnless(HAS_LIB, "precisa da biblioteca openrgb-python")
class TestApi(TempFiles):
    def setUp(self):
        super().setUp()
        self.devs = fake_pc()
        self.more = [mock.patch.object(rc, "client", return_value=FakeClient(self.devs)),
                     mock.patch.object(rc, "openrgb_running", return_value=True),
                     mock.patch.object(rc, "autostart_installed", return_value=False)]
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

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_index_and_state(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn(b"<title>EasyRGB</title>", r.read())
        code, st = self.call("/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(len(st["devices"]), 4)
        self.assertEqual(st["devices"][1]["type"], "DRAM")
        self.assertTrue(st["devices"][0]["effects"])

    def test_preview_apply_preset_share_auto(self):
        body = {"colors": ["#FF0000", "#0000FF"], "brightness": 100, "devices": [0, 1, 2, 3],
                "groups": [{"ids": [1, 2], "mode": "span"}], "ui": {"effect": "static"}}
        code, r = self.call("/api/preview", body)
        self.assertEqual(code, 200)
        self.assertEqual(len(r["report"]), 4)
        self.assertFalse(rc.STATE_FILE.exists())
        self.call("/api/apply", body)
        self.assertTrue(rc.STATE_FILE.exists())

        _, r = self.call("/api/preset", {"name": "Teste", "colors": ["#ABCDEF"]})
        self.assertEqual(r["palettes"]["Teste"], ["#ABCDEF"])
        _, r = self.call("/api/preset", {"name": "Teste", "delete": True})
        self.assertNotIn("Teste", r["palettes"])

        _, r = self.call("/api/share")
        _, look = self.call("/api/share", {"code": r["code"]})
        self.assertEqual(look["look"]["colors"], ["#FF0000", "#0000FF"])

        _, r = self.call("/api/auto", {"games": [{"process": "cs2.exe", "preset": "Counter-Strike 2"}]})
        self.assertEqual(r["auto"]["games"][0]["process"], "cs2.exe")
        _, r = self.call("/api/auto")
        self.assertIn("cs2.exe", r["known"])

    def test_effect_start_stop_and_claude(self):
        base = {"colors": ["#FF0000", "#00FF00"], "brightness": 100, "devices": [0, 1, 2, 3]}
        _, r = self.call("/api/effect", dict(base, on=True, kind="respirar", speed=5))
        self.assertTrue(r["effect"])
        _, st = self.call("/api/claude")
        self.assertEqual(st["effect_kind"], "respirar")
        _, r = self.call("/api/effect", {"on": False})
        self.assertFalse(r["effect"])
        code, r = self.call("/api/claude", {"name": "Teste IA", "colors": ["#FF00FF"], "effect": "static"})
        self.assertEqual(code, 200)
        self.assertEqual(r["profile"]["name"], "Teste IA")

    def test_errors(self):
        code, r = self.call("/api/apply", {"colors": []})
        self.assertEqual(code, 400)   # erro da pessoa (sem cores): mensagem clara, não "erro interno"
        self.assertFalse(r["ok"])
        self.assertIn("cor", r["error"])
        code, _ = self.call("/api/nada")
        self.assertEqual(code, 404)
        code, r = self.call("/api/share", {"code": "lixo"})
        self.assertEqual(code, 400)


# ------------------------------------------------------------------ interface (index.html)
class TestUi(unittest.TestCase):
    html = (APP / "index.html").read_text(encoding="utf-8")

    def test_no_emojis(self):
        emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]")
        self.assertEqual(emoji.findall(self.html), [], "a interface não pode ter emojis")

    def test_icons_exist(self):
        defined = set(re.findall(r"^\s+\"?([\w-]+)\"?:'<", self.html, re.M))
        used = set(re.findall(r'data-ii?="([\w-]+)"', self.html)) | set(re.findall(r'icon\("([\w-]+)"', self.html))
        self.assertEqual(used - defined, set(), "ícones usados mas não definidos")

    def _en_keys(self):
        block = self.html[self.html.index("const EN={"):self.html.index("function tr(")]
        return set(re.findall(r'"((?:[^"\\]|\\.)*)":"', block))

    def test_every_tr_call_has_english(self):
        en = {k.replace('\\"', '"') for k in self._en_keys()}
        used = {s.replace('\\"', '"') for s in re.findall(r'tr\("((?:[^"\\]|\\.)*)"', self.html)}
        maps = re.findall(r"const (?:ACTIONS|FXNAME|MODE)=\{([^}]*)\}", self.html)
        for m in maps:
            used |= set(re.findall(r':"([^"]+)"', m))
        used |= set(re.findall(r'\["\w+","([^"]+)"\]', self.html[self.html.index("const TYPE"):self.html.index("const tIcon")]))
        used |= set(re.findall(r'\["\w+","([^"]+)"\]', self.html[self.html.index("const PERSIST"):self.html.index("function persistHTML")]))
        self.assertEqual(sorted(used - en), [], "textos sem tradução para inglês")

    def test_static_html_has_english(self):
        en = {k.replace('\\"', '"') for k in self._en_keys()}
        body = self.html[self.html.index("<body>"):self.html.index("<script>")]
        texts = {" ".join(m.split()) for m in re.findall(r">([^<>]*[A-Za-zÀ-ú][^<>]*)<", body)}
        texts |= set(re.findall(r'(?:placeholder|title|aria-label)="([^"]+)"', body))
        keep = {"EasyRGB", "v1", "Presets", "Mouse", "Ctrl", "Alt", "E", "L", "°C"}   # iguais nos dois idiomas
        self.assertEqual(sorted(t for t in texts if t and t not in en and t not in keep), [],
                         "texto fixo da página sem tradução para inglês")

    def test_dark_theme_only(self):
        css = self.html[self.html.index("<style>"):self.html.index("</style>")]
        self.assertNotIn("prefers-color-scheme: light", css, "o app usa só o tema escuro")
        self.assertIn("color-scheme:dark", css)

    def test_ids_exist(self):
        ids = set(re.findall(r'id="([\w-]+)"', self.html))
        used = set(re.findall(r'\$\("#([\w-]+)"\)', self.html))
        self.assertEqual(used - ids, set(), "elementos usados no JS que não existem no HTML")


# ------------------------------------------------------------------ paridade Python x JavaScript
NODE = shutil.which("node")
JS_RUNNER = r"""
const fs=require('fs'); const html=fs.readFileSync(process.argv[1],'utf8');
const a=html.indexOf('/* ===================== cor'), b=html.indexOf('function payload(');
const S={}; const code=html.slice(a,b);
const run=new Function('S', code+'; return plan();');
const cases=JSON.parse(fs.readFileSync(0,'utf8')); const out=[];
for(const c of cases){ Object.assign(S,c); S.disabled=new Set(c.disabled||[]); out.push(run(S)); }
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "Node.js não instalado")
class TestResponsive(unittest.TestCase):
    """A tela precisa caber em janelas estreitas e celulares (375 px) sem rolagem para o lado."""
    def setUp(self):
        self.html = (APP / "index.html").read_text(encoding="utf-8")

    def test_has_small_screen_rules(self):
        self.assertIn('name="viewport" content="width=device-width', self.html)
        for w in ("@media(max-width:700px)", "@media(max-width:420px)"):
            self.assertIn(w, self.html)

    def test_no_grid_column_wider_than_a_phone(self):
        css = self.html[: self.html.index("</style>")]
        # o último valor vence: só confere a regra final de cada grade
        for sel in (".perlist", ".devs", ".games"):
            rule = css[css.rindex(sel + "{grid-template-columns"):]
            rule = rule[: rule.index("}")]
            self.assertIn("min(", rule, f"{sel} precisa de min(...,100%) para caber no celular")
        for px in re.findall(r"minmax\((\d+)px", css):
            self.assertLessEqual(int(px), 340)


class TestParity(unittest.TestCase):
    def test_plan_python_equals_js(self):
        devs = [{"id": i, "type": ["MOTHERBOARD", "DRAM", "DRAM", "KEYBOARD"][i],
                 "zones": [{"name": z.name, "leds": len(z.leds)} for z in d.zones]} for i, d in enumerate(fake_pc())]
        cases = []
        for mode in ("gradiente", "alternado", "zona"):
            for links in ({"DRAM": "separate"}, {"DRAM": "mirror"}, {"DRAM": "span"}):
                cases.append({"colors": ["#FF2E88", "#FFB547", "#00D9C8"], "mode": mode, "links": links,
                              "overrides": {"3": {"1": "#FFFFFF", "L10": "#123456"}, "1": {"0": "#00FF00"}} if mode == "zona" else {"3": {"L7": "#ABCDEF"}},
                              "devices": devs, "disabled": [2] if links["DRAM"] == "separate" and mode == "zona" else []})
        res = subprocess.run([NODE, "-e", JS_RUNNER, str(APP / "index.html")], input=json.dumps(cases),
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        js = json.loads(res.stdout)
        fdevs = fake_pc()
        for c, jplan in zip(cases, js):
            ids = [d["id"] for d in devs if d["id"] not in c["disabled"]]
            groups = [{"ids": [1, 2], "mode": c["links"]["DRAM"]}] if c["links"]["DRAM"] != "separate" else []
            py = rc.plan_colors(fdevs, ids, HEX(" ".join(c["colors"])), c["mode"], 0, c["overrides"], groups)
            for i in ids:
                pj = [rc.parse_colors(h)[0] for h in jplan[str(i)]]
                self.assertEqual(len(pj), len(py[i]), f"{c['mode']} {c['links']} dispositivo {i}")
                for a, b in zip(py[i], pj):
                    self.assertTrue(all(abs(x - y) <= 1 for x, y in zip(a, b)),
                                    f"{c['mode']} {c['links']} dispositivo {i}: py {a} js {b}")



# ------------------------------------------------------------------ programas de fabricante e efeitos LED a LED
import vendors  # noqa: E402


class FakeBridge(vendors.LogitechBridge):
    def __init__(self):
        self.painted, self.keys = [], []

    def available(self):
        return True

    def stop(self):
        pass

    def paint(self, dev, cols):
        self.painted.append((dev.name, cols))

    def paint_keys(self, names, cols):
        self.keys.append((names, cols))
        return True


class Led:
    def __init__(self, name):
        self.name = name


class TestVendors(TempFiles):
    def setUp(self):
        super().setUp()
        import vendors
        self.vendors = vendors
        self.br = FakeBridge()
        self.p_env = mock.patch.dict(os.environ, {"EASYRGB_NO_VENDORS": ""})
        self.p_br = mock.patch.object(vendors, "BRIDGES", [self.br])
        self.p_env.start(); self.p_br.start()
        rc._vend.update(t=0.0, devs=[], keys=[], sig=None)

    def tearDown(self):
        self.p_br.stop(); self.p_env.stop()
        rc._vend.update(t=0.0, devs=[], keys=[], sig=None)
        super().tearDown()

    def test_keymap_has_the_whole_keyboard(self):
        km = self.vendors.KEYMAP
        self.assertGreaterEqual(len(km), 100)
        self.assertEqual(self.vendors.key_of("Key: A")["sc"], 0x1E)
        self.assertEqual(self.vendors.key_of("Key: Escape")["vk"], 0x1B)
        self.assertEqual(self.vendors.key_of(r"Key: \ (ANSI)")["sc"], 0x2B)
        self.assertLess(km["q"]["x"], km["p"]["x"])

    @unittest.skipUnless(HAS_LIB, "bibliotecas ainda não instaladas")
    def test_virtual_device_joins_list_and_gets_colors(self):
        c = FakeClient(fake_pc())
        with mock.patch.object(rc, "client", return_value=c):
            devs = rc.all_devices(c)
            self.assertEqual(len(devs), 5)   # 4 do OpenRGB + "todas as luzes Logitech"
            rc.apply(HEX("#FF0000 #0000FF"), 100, persist=False)
        self.assertEqual(self.br.painted[-1][0], "Logitech (G HUB)")
        self.assertEqual(rc.persist_kind(devs[4]), "vendor")
        self.assertEqual(rc.running_conflicts.__name__, "running_conflicts")
        self.assertEqual(rc._bridged(["Logitech G HUB", "Corsair iCUE"]), ["Corsair iCUE"])

    def test_pc_json_picks_devices_and_zones(self):
        rc.save_pc({"vendors": {"logitech": {"devices": [{"type": "mouse", "zones": 2, "name": "G502"}]}}})
        c = FakeClient(fake_pc())
        devs = rc.all_devices(c)
        self.assertEqual(devs[4].name, "G502")
        self.assertEqual(len(devs[4].zones), 2)
        rc.save_pc({"vendors": {"logitech": {"enabled": False}}})
        self.assertEqual(len(rc.all_devices(c)), 4)

    @unittest.skipUnless(HAS_LIB, "bibliotecas ainda não instaladas")
    def test_lights_off_goes_through_ghub(self):
        kb = FakeDev("PRO Gaming Keyboard", 5, [FakeZone("Keyboard", 2)], [FakeMode("Direct", 32, 1)])
        kb.leds = [Led("Key: A"), Led("Key: S")]
        kb.metadata = type("M", (), {"vendor": "Logitech"})()
        c = FakeClient([kb])
        with mock.patch.object(rc, "client", return_value=c):
            rc.all_devices(c)
            rc.turn_off()
        self.assertEqual(self.br.keys[-1][1], [(0, 0, 0), (0, 0, 0)])
        self.assertNotIn(("off",), kb.calls)   # o OpenRGB não mexeu no teclado

    def test_repaints_when_ghub_opens_after_easyrgb(self):
        """Ao ligar o PC o G HUB abre depois: o EasyRGB conecta de novo e repinta o visual salvo."""
        kb = FakeDev("PRO Gaming Keyboard", 5, [FakeZone("Keyboard", 1)], [FakeMode("Direct", 32, 1)])
        kb.metadata = type("M", (), {"vendor": "Logitech"})()
        self.br.ok, self.br.retry_at = False, 0.0
        self.br.restarted = lambda: False
        with mock.patch.object(rc, "openrgb_running", return_value=True),              mock.patch.object(rc, "client", return_value=FakeClient([kb])),              mock.patch.object(rc, "load_state", return_value={"palette": ["#FF0000"]}),              mock.patch.object(rc, "apply_saved") as again:
            rc.vendor_tick()
            again.assert_called_once()
            self.br.ok = True
            again.reset_mock()
            rc.vendor_tick()
            again.assert_not_called()   # conectado e sem reinício: não repinta à toa

    @unittest.skipUnless(HAS_LIB, "bibliotecas ainda não instaladas")
    def test_logitech_keyboard_seen_by_openrgb_goes_through_ghub(self):
        kb = FakeDev("PRO Gaming Keyboard", 5, [FakeZone("Keyboard", 3)], [FakeMode("Direct", 32, 1)])
        kb.leds = [Led("Key: A"), Led("Key: S"), Led("Logo")]
        kb.metadata = type("M", (), {"vendor": "Logitech"})()   # o nome não diz a marca; o OpenRGB diz
        c = FakeClient([kb])
        with mock.patch.object(rc, "client", return_value=c):
            self.assertEqual(len(rc.all_devices(c)), 1)   # não cria o "todas as luzes" de novo
            rc.apply(HEX("#FF0000"), 100, persist=False)
        self.assertEqual(self.br.keys[-1][0], ["Key: A", "Key: S", "Logo"])
        self.assertFalse([x for x in kb.calls if x[0] == "colors"])   # OpenRGB não mexeu (sem conflito)


class TestLogitechStartup(unittest.TestCase):
    """Ao ligar o PC: o G HUB abre depois e recarrega o perfil. O EasyRGB espera e reconecta na hora certa."""
    def setUp(self):
        self.b = vendors.LogitechBridge()
        self.dll = mock.MagicMock()
        self.dll.LogiLedInitWithName.return_value = True
        self.p = [mock.patch.object(vendors.LogitechBridge, "dll_path", return_value=Path("x.dll")),
                  mock.patch.object(vendors, "_pid", return_value=111),
                  mock.patch.object(vendors.ctypes, "WinDLL", return_value=self.dll, create=True),
                  mock.patch.object(vendors.time, "sleep")]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_waits_while_ghub_is_loading(self):
        with mock.patch.object(vendors, "_started_at", return_value=vendors.time.time() - 5):
            self.assertFalse(self.b.start())
        self.dll.LogiLedInitWithName.assert_not_called()

    def test_reconnects_at_each_mark_after_ghub_opens(self):
        now = vendors.time.time()
        with mock.patch.object(vendors, "_started_at", return_value=now - 25):
            self.assertTrue(self.b.start())
        self.assertEqual(self.b.pending, list(vendors.LogitechBridge.REASSERT))
        hits = 0
        for age in (29, 31, 95, 170, 185, 310, 610, 2000):   # o G HUB envelhecendo
            self.b.anchor, self.b.checked = now - age, 0.0
            if self.b.restarted():
                hits += 1
                with mock.patch.object(vendors, "_started_at", return_value=now - 25):
                    self.b.retry_at = 0.0
                    self.assertTrue(self.b.start())   # mesmo G HUB: não reagenda
        self.assertEqual(hits, len(vendors.LogitechBridge.REASSERT))   # uma reconexão por momento, nada mais
        self.assertEqual(self.b.pending, [])
        self.b.checked = 0.0
        self.assertFalse(self.b.restarted())    # já estável: não fica reconectando

    def test_old_ghub_does_not_trigger_reconnects(self):
        with mock.patch.object(vendors, "_started_at", return_value=vendors.time.time() - 5000):
            self.assertTrue(self.b.start())
        self.assertEqual(self.b.pending, [])
        self.b.checked = 0.0
        self.assertFalse(self.b.restarted())

    def test_wake_from_sleep_reconnects_and_restarts_marks(self):
        with mock.patch.object(vendors, "_started_at", return_value=vendors.time.time() - 5000):
            self.assertTrue(self.b.start())
        self.b._wall -= 3600   # relógio pulou 1 h sem o tempo real passar: o PC dormiu
        self.assertTrue(self.b.restarted())
        self.assertFalse(self.b.ok)
        self.assertEqual(self.b.pending, list(vendors.LogitechBridge.REASSERT))

    def test_waits_for_ghub_right_after_boot(self):
        with mock.patch.object(vendors, "uptime", return_value=30), mock.patch.object(vendors, "_running", return_value=False):
            self.assertTrue(self.b.available())
        with mock.patch.object(vendors, "uptime", return_value=3000), mock.patch.object(vendors, "_running", return_value=False):
            self.assertFalse(self.b.available())


class TestSpatialEffects(unittest.TestCase):
    def test_wave_moves_and_respects_direction(self):
        pal = HEX("#FF0000 #0000FF")
        pos = [(0.0, 0.5), (0.5, 0.5)]
        a = rc.wave_colors(pal, pos, 0.0, 3)
        b = rc.wave_colors(pal, pos, 1.0, 3)
        self.assertNotEqual(a, b)
        self.assertEqual(rc._axis(0.2, 0.0, "esquerda"), 0.8)
        self.assertEqual(rc._axis(0.5, 0.0, "centro"), 0.0)

    def test_keyboard_positions_follow_the_layout(self):
        kb = FakeDev("Teclado", 5, [FakeZone("Keyboard", 12)], [])
        kb.leds = [Led("Key: " + k) for k in "QWERTYUIOP"] + [Led("Key: Escape"), Led("Key: Space")]
        pos, real = __import__("vendors").led_positions(kb)
        self.assertTrue(real)
        self.assertLess(pos[0][0], pos[9][0])          # Q fica à esquerda do P
        self.assertLess(pos[10][1], pos[11][1])        # Esc fica acima do Espaço

    def test_stars_and_ripple_stay_in_palette_range(self):
        pal = HEX("#00FF00 #FF00FF")
        pos = [(i / 10, 0.5) for i in range(10)]
        st = rc.star_colors(pal, pos, 1.3, 3, {}, 0)
        self.assertEqual(len(st), 10)
        self.assertTrue(all(0 <= v <= 255 for c in st for v in c))
        rip = rc.ripple_colors(pal, pos, True, 0.1, 3, [(0.5, 0.5, 0.0)])
        self.assertGreater(max(sum(c) for c in rip), sum(rc.scale(pal[0], 8)))
        self.assertEqual(len(set(rc.ripple_colors(pal, pos, False, 0.1, 3, [(0.5, 0.5, 0.0)]))), 1)

    def test_screen_colors_per_key(self):
        from PIL import Image
        im = Image.new("RGB", (22, 6), (0, 0, 255))
        im.putpixel((0, 0), (255, 0, 0))
        self.assertEqual(rc.screen_colors(im, [(0.0, 0.0), (0.9, 0.9)], True), [(255, 0, 0), (0, 0, 255)])
        self.assertEqual(len(rc.screen_colors(None, [(0, 0)], True)), 1)

    def test_each_device_can_have_its_own_effect(self):
        m = rc.effect_map("static", {"pfx": {"3": "onda"}}, [0, 1, 2, 3])
        self.assertEqual(m, {0: "static", 1: "static", 2: "static", 3: "onda"})
        m = rc.effect_map("respirar", {"pfx": {"3": "teclas"}}, [0, 3])
        self.assertEqual(m, {0: "respirar", 3: "teclas"})
        self.assertEqual(rc.effect_map("onda", {"fxdevs": [3]}, [0, 3]), {0: "static", 3: "onda"})  # formato antigo
        self.assertTrue(rc.has_animation({"effect": "static", "pfx": {"3": "onda"}}))
        self.assertFalse(rc.has_animation({"effect": "static", "pfx": {"3": "static"}}))

    def test_effect_colors_for_every_kind(self):
        pal = HEX("#FF0000 #00FF00 #0000FF")
        cols = [(255, 0, 0)] * 6
        pos = [(i / 6, 0.5) for i in range(6)]
        ctx = {"level": 0.5, "shift": 0.3, "stars": {}, "keys": None, "dir": "direita", "shot": None, "idx": 0}
        for k in rc.EFFECTS:
            out = rc.effect_colors(k, pal, cols, pos, False, 1.2, 3, ctx)
            self.assertEqual(len(out), 6, k)
            self.assertTrue(all(0 <= v <= 255 for c in out for v in c), k)

    def test_new_effects_are_known(self):
        for k in ("onda", "estrelas", "tela", "teclas"):
            self.assertIn(k, rc.EFFECTS)
            self.assertIn(k, rc.SPATIAL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
