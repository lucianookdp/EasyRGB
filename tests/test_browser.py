"""Teste de ponta a ponta: a tela real do EasyRGB aberta num navegador sem janela.

Confere que não há erro de JavaScript, que nomes maliciosos (de presets, aparelhos e perfis de IA) não viram
código rodando na página (XSS), que nada passa da largura da tela (computador, tablet e celular) e que clicar
nos botões principais não quebra nada. Precisa de Node.js e Chrome ou Edge; sem eles, o teste é pulado.
"""
import json
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_core import FakeClient, FakeDev, FakeMode, FakeZone, HAS_LIB, fake_pc
from test_robustness import Isolated, ROOT, rc

XSS = '<img src=x onerror="window.__xss=1">'


@unittest.skipUnless(shutil.which("node"), "precisa do Node.js")
@unittest.skipUnless(HAS_LIB, "precisa da biblioteca openrgb-python")
class TestBrowser(Isolated):
    def setUp(self):
        super().setUp()
        devs = fake_pc()
        devs.append(FakeDev(XSS, 5, [FakeZone("Keyboard" + XSS, 4)], [FakeMode("Direct", 32, 1)]))
        (self.tmp / "my_presets.json").write_text(json.dumps({XSS: ["#FF0000", "#0000FF"]}), encoding="utf-8")
        (self.tmp / "pc.json").write_text(json.dumps({"agent": XSS, "summary": XSS, "nicknames": {"0": XSS}}),
                                          encoding="utf-8")
        prof = {"name": XSS, "description": XSS, "colors": ["#FF00FF"], "created": "2026-01-01 10:00:00"}
        (self.tmp / "claude_color.json").write_text(json.dumps({"active": prof, "history": [prof, prof]}),
                                                    encoding="utf-8")
        self.more = [mock.patch.object(rc, "client", return_value=FakeClient(devs)),
                     mock.patch.object(rc, "openrgb_running", return_value=True),
                     mock.patch.object(rc, "autostart_installed", return_value=False),
                     mock.patch.object(rc, "running_conflicts", return_value=[XSS]),
                     mock.patch.object(rc, "sync_hotkeys")]
        for p in self.more:
            p.start()
        self.srv = rc.Server(("127.0.0.1", 0), rc.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        for p in self.more:
            p.stop()
        super().tearDown()

    def test_page_in_a_real_browser(self):
        r = subprocess.run(["node", str(ROOT / "tests" / "browser_check.mjs"), self.url], capture_output=True,
                           text=True, timeout=180)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        if out.get("skip"):
            self.skipTest(out["skip"])
        self.assertEqual(out["errors"], [], "erros na página")
        for w, info in out["widths"].items():
            with self.subTest(width=w):
                self.assertFalse(info["xss"], "código injetado rodou na página")
                self.assertLessEqual(info["scroll"], info["client"] + 1, "a página passa da largura da tela")
                self.assertTrue(info["connected"])
        self.assertGreater(out["clicks"], 10)
        self.assertFalse(out["xss_after_clicks"])


if __name__ == "__main__":
    unittest.main()
