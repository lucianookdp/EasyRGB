"""Pontes com programas RGB de fabricantes e mapa do teclado.

Em vez de brigar com o programa do fabricante (G HUB, iCUE, Synapse...), o EasyRGB fala com ele pelo
kit oficial (SDK) que o próprio programa oferece para jogos e aplicativos. O programa continua aberto e o
EasyRGB pinta por cima; quando o EasyRGB solta o controle, o programa volta ao perfil dele.

Cada ponte vira "dispositivos virtuais" que se comportam igual aos do OpenRGB (nome, zonas, LEDs,
set_colors), então paleta, efeitos e automações funcionam neles sem código especial.
"""
import ctypes
import os
import subprocess
import threading
from pathlib import Path

# ---------------------------------------------------------------- mapa do teclado
# nome da tecla no OpenRGB | coluna | linha | código virtual do Windows | scan code (= KeyName do SDK Logitech)
_KEYS = """
Escape 0 0 1B 01|F1 2 0 70 3B|F2 3 0 71 3C|F3 4 0 72 3D|F4 5 0 73 3E|F5 6.5 0 74 3F|F6 7.5 0 75 40|F7 8.5 0 76 41
F8 9.5 0 77 42|F9 11 0 78 43|F10 12 0 79 44|F11 13 0 7A 57|F12 14 0 7B 58|Print Screen 15.5 0 2C 137
Scroll Lock 16.5 0 91 46|Pause/Break 17.5 0 13 145
` 0 1 C0 29|1 1 1 31 02|2 2 1 32 03|3 3 1 33 04|4 4 1 34 05|5 5 1 35 06|6 6 1 36 07|7 7 1 37 08|8 8 1 38 09
9 9 1 39 0A|0 10 1 30 0B|- 11 1 BD 0C|= 12 1 BB 0D|Backspace 13.5 1 08 0E|Insert 15.5 1 2D 152|Home 16.5 1 24 147
Page Up 17.5 1 21 149|Num Lock 19 1 90 45|Number Pad / 20 1 6F 135|Number Pad * 21 1 6A 37|Number Pad - 22 1 6D 4A
Tab 0.25 2 09 0F|Q 1.5 2 51 10|W 2.5 2 57 11|E 3.5 2 45 12|R 4.5 2 52 13|T 5.5 2 54 14|Y 6.5 2 59 15|U 7.5 2 55 16
I 8.5 2 49 17|O 9.5 2 4F 18|P 10.5 2 50 19|[ 11.5 2 DB 1A|] 12.5 2 DD 1B|\\ (ANSI) 13.75 2 DC 2B|Delete 15.5 2 2E 153
End 16.5 2 23 14F|Page Down 17.5 2 22 151|Number Pad 7 19 2 67 47|Number Pad 8 20 2 68 48|Number Pad 9 21 2 69 49
Number Pad + 22 2.5 6B 4E
Caps Lock 0.4 3 14 3A|A 1.75 3 41 1E|S 2.75 3 53 1F|D 3.75 3 44 20|F 4.75 3 46 21|G 5.75 3 47 22|H 6.75 3 48 23
J 7.75 3 4A 24|K 8.75 3 4B 25|L 9.75 3 4C 26|; 10.75 3 BA 27|' 11.75 3 DE 28|# 12.75 3 DC 2B|Enter 13.4 3 0D 1C
Number Pad 4 19 3 64 4B|Number Pad 5 20 3 65 4C|Number Pad 6 21 3 66 4D
Left Shift 0.6 4 A0 2A|\\ (ISO) 1.25 4 E2 56|Z 2.25 4 5A 2C|X 3.25 4 58 2D|C 4.25 4 43 2E|V 5.25 4 56 2F|B 6.25 4 42 30
N 7.25 4 4E 31|M 8.25 4 4D 32|, 9.25 4 BC 33|. 10.25 4 BE 34|/ 11.25 4 BF 35|Right Shift 13.1 4 A1 36
Up Arrow 16.5 4 26 148|Number Pad 1 19 4 61 4F|Number Pad 2 20 4 62 50|Number Pad 3 21 4 63 51|Number Pad Enter 22 4.5 - 11C
Left Control 0.6 5 A2 1D|Left Windows 1.9 5 5B 15B|Left Alt 3.1 5 A4 38|Space 6.5 5 20 39|Right Alt 9.9 5 A5 138
Right Fn 11.1 5 - -|Right Windows 11.1 5 5C 15C|Menu 12.4 5 5D 15D|Right Control 13.6 5 A3 11D
Left Arrow 15.5 5 25 14B|Down Arrow 16.5 5 28 150|Right Arrow 17.5 5 27 14D|Number Pad 0 19.5 5 60 52
Number Pad . 21 5 6E 53
"""
KEY_W, KEY_H = 22.0, 5.0


def _parse_keys():
    out = {}
    for item in _KEYS.replace("\n", "|").split("|"):
        parts = item.strip().split(" ")
        if len(parts) < 5:
            continue
        name, x, y, vk, sc = " ".join(parts[:-4]), *parts[-4:]
        out[name.lower()] = {"name": name, "x": float(x), "y": float(y),
                             "vk": None if vk == "-" else int(vk, 16), "sc": None if sc == "-" else int(sc, 16)}
    return out


KEYMAP = _parse_keys()
_SPECIAL = {"logo": (11.0, -0.8), "g logo": (11.0, -0.8), "lighting": (19.0, -0.8), "game mode": (20.0, -0.8)}


def key_of(led_name):
    """Dados da tecla a partir do nome do LED no OpenRGB ("Key: A" -> A)."""
    n = str(led_name or "").strip().lower()
    if n.startswith("key:"):
        n = n[4:].strip()
    return KEYMAP.get(n)


def led_positions(dev):
    """Posição (x, y) de 0 a 1 de cada LED do dispositivo, para efeitos como a onda.
    Teclados usam o mapa físico das teclas; o resto segue a ordem dos LEDs (x) e das zonas (y)."""
    leds = getattr(dev, "leds", None) or []
    zones = getattr(dev, "zones", None) or []
    total = sum(len(z.leds) for z in zones) or len(leds)
    pos, k = [], 0
    hits = 0
    for zi, z in enumerate(zones):
        n = len(z.leds)
        for j in range(n):
            name = getattr(leds[k], "name", "") if k < len(leds) else ""
            key = key_of(name)
            sp = _SPECIAL.get(str(name).strip().lower())
            if key:
                pos.append((key["x"] / KEY_W, key["y"] / KEY_H)); hits += 1
            elif sp:
                pos.append((sp[0] / KEY_W, 0.0)); hits += 1
            else:
                pos.append(((k + 0.5) / max(1, total) if total > 1 else 0.5, (zi + 0.5) / max(1, len(zones))))
            k += 1
    return pos, hits > 8   # True = posições reais de teclado


# ---------------------------------------------------------------- dispositivos virtuais
class _Led:
    def __init__(self, name):
        self.name = name


class _Zone:
    def __init__(self, name, leds):
        self.name = name
        self.leds = [_Led(f"{name} {i + 1}" if leds > 1 else name) for i in range(leds)]


class VirtualDevice:
    """Imita um dispositivo do openrgb-python, mas manda as cores por uma ponte de fabricante."""
    modes, active_mode = [], 0

    def __init__(self, bridge, name, dtype, zones, target):
        self.bridge, self.name, self.type, self.target = bridge, name, dtype, target
        self.zones = [_Zone(zn, n) for zn, n in zones]
        self.leds = [l for z in self.zones for l in z.leds]
        self.backend = bridge.key
        self.persist = "vendor"

    def set_colors(self, colors, fast=False):
        cols = [(c.red, c.green, c.blue) if hasattr(c, "red") else tuple(c) for c in colors]
        self.bridge.paint(self, cols)

    def set_mode(self, *a, **k):
        pass

    def save_mode(self):
        pass

    def off(self):
        self.bridge.paint(self, [(0, 0, 0)] * len(self.leds))


# ---------------------------------------------------------------- Logitech G HUB
def _running(*names):
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=8).stdout.lower()
    except Exception:
        return False
    return any(n.lower() in out for n in names)


class LogitechBridge:
    """G HUB aberto + "Permitir que jogos e aplicativos controlem a iluminação" ligado no G HUB."""
    key, app = "logitech", "Logitech G HUB"
    # tipos de dispositivo do SDK (LogiLed::DeviceType) para cor por zona
    ZONE_TYPES = {"keyboard": 0, "mouse": 3, "mousemat": 4, "headset": 8, "speaker": 14}
    OPENRGB_TYPE = {"keyboard": 5, "mouse": 6, "mousemat": 7, "headset": 8, "speaker": 12, "all": 19}

    def __init__(self):
        self.dll, self.ok, self.lock = None, False, threading.Lock()

    @staticmethod
    def dll_path():
        cands = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LGHUB" / "sdks" / "sdk_legacy_led_x64.dll"]
        try:
            import winreg
            for root in (r"SOFTWARE\Classes\CLSID", r"SOFTWARE\Classes\WOW6432Node\CLSID"):
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    root + r"\{a6519e67-7632-4375-afdf-caa889744403}\ServerBinary") as k:
                    p = Path(winreg.QueryValue(k, None))
                    if p.name.endswith("x64.dll"):
                        cands.insert(0, p)
        except Exception:
            pass
        return next((p for p in cands if p.exists()), None)

    def available(self):
        return self.dll_path() is not None and _running("lghub_agent.exe", "lghub.exe")

    def start(self):
        with self.lock:
            if self.ok:
                return True
            p = self.dll_path()
            if not p:
                return False
            d = ctypes.WinDLL(str(p))
            d.LogiLedInitWithName.argtypes = [ctypes.c_char_p]
            for fn in ("LogiLedInitWithName", "LogiLedSetTargetDevice", "LogiLedSetLighting",
                       "LogiLedSetLightingForKeyWithKeyName", "LogiLedSetLightingForTargetZone"):
                getattr(d, fn).restype = ctypes.c_bool
            if not d.LogiLedInitWithName(b"EasyRGB"):
                return False
            self.dll, self.ok = d, True
            return True

    def stop(self):
        """Devolve a iluminação ao G HUB (ele volta ao perfil dele)."""
        with self.lock:
            if self.ok:
                try:
                    self.dll.LogiLedShutdown()
                except Exception:
                    pass
            self.ok = False

    @staticmethod
    def _pct(c):
        return [round(v * 100 / 255) for v in c]

    def devices(self, cfg):
        """cfg (do pc.json, escrito pela IA): [{"type": "mouse", "zones": 2, "name": "G502"}, ...].
        Sem configuração: um dispositivo "todas as luzes Logitech" com 1 cor."""
        items = cfg or [{"type": "all", "zones": 1, "name": "Logitech (G HUB)"}]
        out = []
        for it in items:
            t = str(it.get("type", "all")).lower()
            n = max(1, min(8, int(it.get("zones", 1))))
            name = it.get("name") or f"Logitech {t}"
            zones = [("Zona %d" % (i + 1) if n > 1 else "Luz", 1) for i in range(n)]
            out.append(VirtualDevice(self, name, self.OPENRGB_TYPE.get(t, 19), zones, t))
        return out

    def paint(self, dev, cols):
        if not cols or not self.start():
            return
        d = self.dll
        with self.lock:
            if dev.target == "all" or dev.target not in self.ZONE_TYPES:
                d.LogiLedSetTargetDevice(7)   # todos os dispositivos Logitech
                d.LogiLedSetLighting(*self._pct(cols[0]))
                return
            d.LogiLedSetTargetDevice(7)
            for zi, c in enumerate(cols):
                d.LogiLedSetLightingForTargetZone(self.ZONE_TYPES[dev.target], zi, *self._pct(c))

    def paint_keys(self, led_names, cols):
        """Teclado Logitech que o OpenRGB enxerga: pinta tecla por tecla pelo G HUB (sem conflito)."""
        if not self.start():
            return False
        d = self.dll
        with self.lock:
            d.LogiLedSetTargetDevice(4)   # teclados com cor por tecla
            for name, c in zip(led_names, cols):
                k = key_of(name)
                if k and k["sc"] is not None:
                    d.LogiLedSetLightingForKeyWithKeyName(k["sc"], *self._pct(c))
                elif str(name).strip().lower() in ("logo", "g logo"):
                    d.LogiLedSetLightingForKeyWithKeyName(0xFFFF1, *self._pct(c))
        return True


BRIDGES = [LogitechBridge()]
# Próximas pontes (mesmo formato): Razer Chroma (REST em localhost:54235), SteelSeries GameSense
# (JSON local), Corsair iCUE SDK e ASUS Aura SDK. A IA ativa só as que existem no PC (pc.json -> "vendors").


def bridge(key):
    return next((b for b in BRIDGES if b.key == key), None)


def detect_bridges():
    """Quais pontes este PC tem (kit do fabricante instalado e programa aberto). Usado pela IA na instalação."""
    return [{"key": b.key, "app": b.app, "installed": b.dll_path() is not None, "running": b.available()}
            for b in BRIDGES]
