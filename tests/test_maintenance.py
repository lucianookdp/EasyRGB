"""Backup/importar, diagnóstico (só para agentes) e 'Desfazer tudo' — sem tocar no PC de verdade."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import rgb_controller as rc  # noqa: E402

HTML = (ROOT / "app" / "index.html").read_text(encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(rc, "HERE", self.tmp),
                        mock.patch.object(rc, "save_auto", side_effect=lambda a: (self.tmp / "automations.json").write_text(json.dumps(a))),
                        mock.patch.object(rc, "apply_saved"), mock.patch.object(rc, "sync_hotkeys")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, data):
        (self.tmp / name).write_text(json.dumps(data), encoding="utf-8")


class TestBackup(Base):
    def test_roundtrip(self):
        self.write("pc.json", {"agent": "x"})
        self.write("last_state.json", {"colors": ["#ff0000"]})
        self.write("my_presets.json", [{"name": "A"}])
        b = rc.make_backup()
        self.assertEqual(b["easyrgb_backup"], 1)
        self.assertEqual(b["version"], rc.VERSION)
        self.assertEqual(b["pc"], {"agent": "x"})
        self.assertNotIn("automations", b)          # arquivo que não existe fica de fora
        self.write("last_state.json", {"colors": ["#00ff00"]})
        done = rc.restore_backup(b)
        self.assertEqual(sorted(done), ["look", "my_presets", "pc"])
        self.assertEqual(json.loads((self.tmp / "last_state.json").read_text())["colors"], ["#ff0000"])
        before = json.loads((self.tmp / "antes-de-restaurar.json").read_text())   # cópia de segurança
        self.assertEqual(before["look"]["colors"], ["#00ff00"])
        rc.apply_saved.assert_called_once()

    def test_automations_go_through_save_auto(self):
        rc.restore_backup({"easyrgb_backup": 1, "automations": {"games": []}}, apply_now=False)
        rc.save_auto.assert_called_once_with({"games": []})
        rc.apply_saved.assert_not_called()

    def test_rejects_other_files(self):
        for bad in ({}, {"easyrgb_backup": 2}, [], "x", None):
            with self.assertRaises(ValueError):
                rc.restore_backup(bad)
        self.assertFalse((self.tmp / "antes-de-restaurar.json").exists())


class TestDiagnostics(Base):
    def test_report_never_crashes(self):
        with mock.patch.object(rc, "openrgb_running", side_effect=RuntimeError("boom")), \
             mock.patch.object(rc, "device_info", return_value=[]), \
             mock.patch.object(rc, "check_update", return_value={"update": False}), \
             mock.patch.object(rc.subprocess, "run", return_value=mock.Mock(returncode=0)):
            rep = rc.diagnostics()
        self.assertIn("ERRO", rep["openrgb_running"])          # uma checagem que falha não derruba as outras
        self.assertEqual(rep["devices"], [])
        self.assertTrue(rep["pawnio_service"])
        for k in ("easyrgb", "python", "windows", "autostart_ok", "bridges", "conflicts", "hotkeys", "log_tail"):
            self.assertIn(k, rep)
        json.dumps(rep, default=str)

    def test_hidden_from_ui(self):
        self.assertNotIn("diagnostico", HTML)
        self.assertNotIn("/api/diag", HTML)
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("rgb_controller.py diagnostico", agents)
        self.assertIn("restaurar", agents)


class TestUndo(Base):
    def test_undo_keeps_data_by_default(self):
        self.write("pc.json", {"agent": "x"})
        cfg = self.tmp / "claude_desktop_config.json"
        cfg.write_text(json.dumps({"mcpServers": {"easyrgb": {}, "other": {}}}))
        with mock.patch.object(rc, "stop_effect"), mock.patch.object(rc.subprocess, "run") as run, \
             mock.patch.object(rc, "autostart_installed", return_value=False), \
             mock.patch("mcp_server.claude_desktop_configs", return_value=[cfg]), \
             mock.patch("tempfile.gettempdir", return_value=str(self.tmp)):
            done = rc.undo_everything()
        self.assertTrue(done["autostart_removed"])
        self.assertEqual(json.loads(cfg.read_text())["mcpServers"], {"other": {}})   # só tira o EasyRGB
        self.assertTrue((self.tmp / "pc.json").exists())
        script = (self.tmp / "easyrgb_desfazer.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Unregister-ScheduledTask", script)
        self.assertIn("Enable-ScheduledTask -TaskName AsrPolychromeRGB", script)
        self.assertIn("-Verb RunAs", run.call_args[0][0][-1])

    def test_undo_delete_data_keeps_last_copy(self):
        self.write("pc.json", {"agent": "x"})
        with mock.patch.object(rc, "stop_effect"), mock.patch.object(rc.subprocess, "run"), \
             mock.patch.object(rc, "autostart_installed", return_value=False), \
             mock.patch("mcp_server.claude_desktop_configs", return_value=[]), \
             mock.patch("tempfile.gettempdir", return_value=str(self.tmp)):
            done = rc.undo_everything(delete_data=True)
        self.assertTrue(done["data_deleted"])
        self.assertFalse((self.tmp / "pc.json").exists())
        self.assertEqual(json.loads((self.tmp / "antes-de-desfazer.json").read_text())["pc"], {"agent": "x"})


class TestUI(unittest.TestCase):
    def test_menu_and_double_confirmation(self):
        for i in ('id="exportBtn"', 'id="importCfgBtn"', 'id="undoBtn"', 'id="importFile"', 'id="ask"', 'id="undoData"'):
            self.assertIn(i, HTML)
        self.assertIn('"Tem certeza?"', HTML)
        self.assertIn('confirm:"DESFAZER"', HTML)
        self.assertIn("wait:3", HTML)                       # botão final só libera depois de 3 s
        self.assertNotIn('id="undoData" checked', HTML)     # apagar dados vem desmarcado

    def test_undo_route_needs_confirm(self):
        src = (ROOT / "app" / "rgb_controller.py").read_text(encoding="utf-8")
        self.assertIn('body.get("confirm") != "DESFAZER"', src)


class TestPackaging(unittest.TestCase):
    def test_winget_manifests(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import winget_manifest as wm
        m = wm.manifests("9.9.9", "AB" * 32)
        self.assertEqual(len(m), 3)
        inst = m["lucianookdp.EasyRGB.installer.yaml"]
        self.assertIn("releases/download/v9.9.9/EasyRGB-Setup.exe", inst)
        self.assertIn("InstallerType: inno", inst)
        self.assertIn("Scope: user", inst)
        self.assertEqual(wm.version_from_code(), rc.VERSION)

    def test_hardware_issue_form(self):
        form = (ROOT / ".github" / "ISSUE_TEMPLATE" / "hardware-test.yml").read_text(encoding="utf-8")
        for brand in ("ASUS", "MSI", "Razer", "Corsair", "HyperX", "NZXT", "Cooler Master", "SteelSeries", "Gigabyte"):
            self.assertIn(brand, form)
        self.assertIn("hardware-test.yml", (ROOT / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
