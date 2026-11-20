"""'Conectar a uma IA': as IAs mais usadas com um clique, sem estragar a configuração que a pessoa já tem."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import mcp_server as m  # noqa: E402

CMD = {"command": r"C:\Users\x\AppData\Local\Programs\EasyRGB\EasyRGB.exe", "args": ["--mcp"]}


class TestAIApps(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        env = {"USERPROFILE": str(self.tmp / "home"), "APPDATA": str(self.tmp / "roaming"),
               "LOCALAPPDATA": str(self.tmp / "local")}
        self.p = [mock.patch.dict(os.environ, env), mock.patch.object(m, "server_command", return_value=dict(CMD))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_most_used_apps_listed(self):
        keys = [c["key"] for c in m.list_clients()]
        for k in ("claude-desktop", "claude-code", "cursor", "copilot", "windsurf", "gemini", "codex"):
            self.assertIn(k, keys)
        self.assertFalse(any(c["found"] or c["connected"] for c in m.list_clients()))   # PC vazio

    def test_every_app_connects_and_disconnects(self):
        for c in m.ai_clients():
            files = m.connect_client(c["key"])
            self.assertTrue(files, c["key"])
            m.connect_client(c["key"])   # de novo: não duplica
            if c["kind"] == "toml":
                text = files[0].read_text(encoding="utf-8")
                self.assertEqual(text.count("[mcp_servers.easyrgb]"), 1)
                self.assertIn("command = '" + CMD["command"] + "'", text)   # barra invertida intacta
            else:
                d = json.loads(files[0].read_text(encoding="utf-8"))
                self.assertEqual(d[c["section"]]["easyrgb"]["command"], CMD["command"])
        self.assertTrue(all(c["connected"] for c in m.list_clients()))
        self.assertEqual(len(set(m.disconnect_all())), len(m.ai_clients()))
        self.assertFalse(any(c["connected"] for c in m.list_clients()))

    def test_keeps_other_servers_and_settings(self):
        code = self.tmp / "home" / ".claude.json"
        code.parent.mkdir(parents=True)
        code.write_text(json.dumps({"numStartups": 9, "mcpServers": {"other": {"command": "x"}}}))
        m.connect_client("claude-code")
        d = json.loads(code.read_text())
        self.assertEqual(d["numStartups"], 9)
        self.assertEqual(set(d["mcpServers"]), {"other", "easyrgb"})
        self.assertEqual(d["mcpServers"]["easyrgb"]["type"], "stdio")
        vs = m.connect_client("copilot")[0]
        self.assertIn("servers", json.loads(vs.read_text()))   # VS Code usa "servers", não "mcpServers"

    def test_codex_toml_keeps_the_rest(self):
        cfg = self.tmp / "home" / ".codex" / "config.toml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text('model = "gpt-5"\n\n[mcp_servers.other]\ncommand = "x"\n', encoding="utf-8")
        m.connect_client("codex")
        m.disconnect_all()
        text = cfg.read_text(encoding="utf-8")
        self.assertIn('model = "gpt-5"', text)
        self.assertIn("[mcp_servers.other]", text)
        self.assertNotIn("easyrgb", text)

    def test_broken_json_is_never_overwritten(self):
        cur = self.tmp / "home" / ".cursor" / "mcp.json"
        cur.parent.mkdir(parents=True)
        cur.write_text("{ oops", encoding="utf-8")
        with self.assertRaises(ValueError):
            m.connect_client("cursor")
        self.assertEqual(cur.read_text(encoding="utf-8"), "{ oops")
        self.assertTrue(next(c for c in m.list_clients() if c["key"] == "cursor")["found"])

    def test_unknown_app(self):
        with self.assertRaises(ValueError):
            m.connect_client("chatgpt")

    def test_manual_config(self):
        j = json.loads(m.manual_config()["json"])
        self.assertEqual(j["mcpServers"]["easyrgb"], CMD)


class TestAIAppsUI(unittest.TestCase):
    def test_ui(self):
        html = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
        for need in ('id="aiApps"', 'id="aiList"', 'id="aiManual"', 'class="noai"', "/api/ai-apps"):
            self.assertIn(need, html)
        for key in ("claude-desktop", "claude-code", "cursor", "copilot", "windsurf", "gemini", "codex", "lmstudio"):
            self.assertIn(f'"{key}":', html)   # dica para cada IA


if __name__ == "__main__":
    unittest.main()
