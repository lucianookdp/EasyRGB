"""Teste no hardware REAL (opcional). As luzes piscam por alguns segundos e voltam ao visual salvo no final.

Rodar:  set MEURGB_HW=1 && python -m unittest tests.test_hardware -v
Precisa do OpenRGB aberto (MeuRGB.bat ou "python app/rgb_controller.py conectar").
"""
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rgb_controller as rc  # noqa: E402


@unittest.skipUnless(os.environ.get("MEURGB_HW") == "1", "defina MEURGB_HW=1 para testar no hardware real")
class TestRealHardware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not rc.openrgb_running():
            raise unittest.SkipTest("OpenRGB não está aberto")
        cls.devs = rc.device_info()
        cls.saved = rc.load_state()

    @classmethod
    def tearDownClass(cls):
        rc.stop_effect()
        if cls.saved:
            rc.apply_saved(cls.saved)

    def test_1_devices_found(self):
        self.assertTrue(self.devs, "nenhum dispositivo RGB detectado")
        for d in self.devs:
            self.assertTrue(d["zones"], d["name"])

    def test_2_every_device_accepts_colors(self):
        for pal in ("#FF0000", "#00FF00", "#0000FF #FF00FF"):
            rep = rc.apply(rc.parse_colors(pal), 100, persist=False)
            bad = [r for r in rep if not r["ok"]]
            self.assertEqual(bad, [], f"falhou com {pal}")
            time.sleep(0.6)

    def test_3_groups_and_zone_override(self):
        types = [d["type"] for d in self.devs]
        ids = [d["id"] for d in self.devs if types.count(d["type"]) > 1]
        groups = [{"ids": ids, "mode": "span"}] if len(ids) > 1 else []
        rep = rc.apply(rc.parse_colors("#FF2E88 #00D9C8"), 100, groups=groups,
                       overrides={"0": {"0": "#FFFFFF"}}, persist=False)
        self.assertTrue(all(r["ok"] for r in rep))

    def test_4_one_chip_effect_per_device(self):
        hw = {str(d["id"]): {"mode": d["effects"][0]["name"], "speed": 60} for d in self.devs if d["effects"]}
        rep = rc.apply(rc.parse_colors("#9B3DFF #00D9C8"), 100, hw=hw, persist=False)
        self.assertTrue(all(r["ok"] for r in rep), rep)
        time.sleep(1.5)
        rep = rc.apply(rc.parse_colors("#9B3DFF"), 100, persist=False)  # volta ao modo de cor fixa
        self.assertTrue(all(r["ok"] for r in rep), rep)

    def test_5_app_effect_runs(self):
        rc.start_effect(rc.parse_colors("#FF0000 #0000FF"), 100, "gradiente", None, 8, kind="respirar")
        time.sleep(2)
        self.assertTrue(rc._effect["on"])
        rc.stop_effect()
        self.assertFalse(rc._effect["on"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
