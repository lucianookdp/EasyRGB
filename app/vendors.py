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
import time
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
    if getattr(dev, "positions", None):
        return list(dev.positions), getattr(dev, "type", None) == 5
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
def _log(msg):
    """Anota no easyrgb.log o que a ponte fez (ajuda a entender um teclado apagado depois)."""
    try:
        print(time.strftime("%H:%M:%S"), "[ponte]", msg, flush=True)
    except Exception:
        pass


def _pid(image):
    """PID do processo (ou None). Serve para saber se o programa do fabricante reiniciou."""
    try:
        pids = process_table().get(image.lower())
        return min(pids) if pids else None
    except Exception:
        pass
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=8).stdout
        for line in out.splitlines():
            parts = [x.strip('"') for x in line.split('","')]
            if len(parts) > 1 and parts[0].lower() == image.lower():
                return int(parts[1])
    except Exception:
        pass
    return None


def _started_at(pid):
    """Hora (epoch) em que o processo abriu, ou None."""
    try:
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        c, e, k, u = (ctypes.c_ulonglong() for _ in range(4))
        good = k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u))
        k32.CloseHandle(h)
        return c.value / 1e7 - 11644473600 if good else None
    except Exception:
        return None


def uptime():
    """Segundos desde que o Windows ligou."""
    try:
        f = ctypes.windll.kernel32.GetTickCount64
        f.restype = ctypes.c_ulonglong
        return f() / 1000.0
    except Exception:
        return 1e9


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong), ("th32ProcessID", ctypes.c_ulong),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong),
                ("szExeFile", ctypes.c_wchar * 260)]


def process_table():
    """{nome.exe em minúsculas: [pids]} lido direto do Windows (~1 ms; o tasklist abre um processo e leva ~100 ms)."""
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)   # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        raise OSError("snapshot")
    out = {}
    try:
        e = _PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(ctypes.c_void_p(snap), ctypes.byref(e))
        while ok:
            out.setdefault(e.szExeFile.lower(), []).append(int(e.th32ProcessID))
            ok = k32.Process32NextW(ctypes.c_void_p(snap), ctypes.byref(e))
    finally:
        k32.CloseHandle(ctypes.c_void_p(snap))
    return out


def _running(*names):
    try:
        procs = process_table()
        return any(n.lower() in procs for n in names)
    except Exception:
        pass
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

    AGENT = "lghub_agent.exe"
    SETTLE = 20     # o G HUB acabou de abrir: espera ele terminar de carregar antes de conectar
    # Depois que o G HUB abre (ou o PC volta da suspensão) ele pode reassumir o teclado minutos depois. Nesses
    # momentos o EasyRGB repinta tudo pela mesma conexão. Desconectar e conectar de novo várias vezes deixava o
    # teclado apagado/fraco (o G HUB ficava com sessões velhas), então só reconecta se o G HUB reabrir.
    REASSERT = (30, 90, 180, 300, 600)   # segundos depois do G HUB abrir / do PC acordar
    SLEPT = 30      # relógio andou mais que isto além do tempo real entre duas olhadas: o PC dormiu
    BOOT = 180      # logo depois de ligar o PC, espera o G HUB em vez de mexer no teclado pelo OpenRGB

    def __init__(self):
        self.dll, self.ok, self.lock = None, False, threading.RLock()
        self.pid, self.retry_at, self.fails, self.checked = None, 0.0, 0, 0.0
        self.born, self.anchor, self.pending = 0.0, 0.0, []
        self._wall, self._mono = time.time(), time.monotonic()
        self.connects = 0
        self.repaint = False   # hora de repintar (o G HUB pode ter reassumido o teclado)

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

    routes_keys = True

    def installed(self):
        return self.dll_path() is not None

    def available(self):
        if self.dll_path() is None:
            return False
        # ao ligar o PC o G HUB abre depois do EasyRGB: o teclado espera por ele (não briga pelo OpenRGB)
        return _running("lghub_agent.exe", "lghub.exe") or uptime() < self.BOOT

    def _woke(self):
        """True se o PC dormiu desde a última olhada (o relógio pulou mais que o tempo que passou de fato)."""
        wall, mono = time.time(), time.monotonic()
        slept = (wall - self._wall) - (mono - self._mono) > self.SLEPT
        self._wall, self._mono = wall, mono
        return slept

    def restarted(self):
        """True só quando é preciso conectar de novo: o G HUB fechou ou reabriu. O PC acordar ou chegar um dos
        momentos em que o G HUB costuma reassumir o teclado (REASSERT) só pede uma repintura (take_repaint).
        Olha a cada 5 s."""
        with self.lock:
            woke = self._woke()
            if woke:   # ao acordar, o G HUB repinta o perfil dele: recomeça a sequência de repinturas
                self.anchor, self.pending = time.time(), list(self.REASSERT)
                self.repaint = True
            if not self.ok or time.time() - self.checked < 5:
                return False
            self.checked = time.time()
            due = [m for m in self.pending if time.time() - self.anchor >= m]
            if due:
                self.pending = [m for m in self.pending if m not in due]
                self.repaint = True
            if _pid(self.AGENT) != self.pid:
                _log("G HUB reabriu: reconectando")
                self.stop()
                return True
            return False

    def take_repaint(self):
        """True uma vez depois de cada momento de repintar (e zera o aviso)."""
        r, self.repaint = getattr(self, "repaint", False), False
        return r

    def start(self):
        with self.lock:
            if self.ok:
                self.restarted()
            if self.ok:
                return True
            if time.time() < self.retry_at:   # G HUB ainda abrindo: tenta de novo daqui a pouco
                return False
            self.retry_at = time.time() + 3
            p = self.dll_path()
            pid = _pid(self.AGENT)
            if not p or not pid:
                return False
            born = _started_at(pid) or 0.0
            if time.time() - born < self.SETTLE:
                self.retry_at = born + self.SETTLE
                return False
            d = self.dll or ctypes.WinDLL(str(p))
            d.LogiLedInitWithName.argtypes = [ctypes.c_char_p]
            for fn in ("LogiLedInitWithName", "LogiLedSetTargetDevice", "LogiLedSetLighting",
                       "LogiLedSetLightingForKeyWithKeyName", "LogiLedSetLightingForTargetZone"):
                getattr(d, fn).restype = ctypes.c_bool
            self.dll = d
            if not d.LogiLedInitWithName(b"EasyRGB"):
                # sessão velha presa no G HUB (o app fechou sem se despedir): solta e tenta de novo
                try:
                    d.LogiLedShutdown()
                except Exception:
                    pass
                if not d.LogiLedInitWithName(b"EasyRGB"):
                    _log("G HUB recusou a conexão; tento de novo em 3 s")
                    return False
            time.sleep(0.4)   # o G HUB leva um instante para aceitar comandos depois de conectar
            self.ok, self.pid, self.fails, self.checked = True, pid, 0, time.time()
            if born != self.born:   # G HUB novo (ligou o PC ou ele reabriu): agenda as reconexões
                self.born, self.anchor = born, born
                self.pending = [m for m in self.REASSERT if time.time() - born < m]
            self.connects += 1
            _log(f"G HUB conectado (conexão {self.connects})")
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
            d.LogiLedSetTargetDevice(7)   # todos os dispositivos Logitech
            if dev.target == "all" or dev.target not in self.ZONE_TYPES:
                good = bool(d.LogiLedSetLighting(*self._pct(cols[0])))
            else:
                good = False
                for zi, c in enumerate(cols):
                    good = bool(d.LogiLedSetLightingForTargetZone(self.ZONE_TYPES[dev.target], zi,
                                                                  *self._pct(c))) or good
            self._result(good)

    def _result(self, good):
        """Conta pinturas recusadas seguidas. O SetTargetDevice responde "ok" mesmo com a sessão morta, então só
        as chamadas de cor dizem se o G HUB ainda está ouvindo; 5 recusas seguidas = reconecta."""
        self.fails = 0 if good else self.fails + 1
        if self.fails >= 5:
            _log("G HUB parou de aceitar as cores: reconectando")
            self.fails = 0
            self.stop()
            return False
        return True

    def paint_keys(self, led_names, cols):
        """Teclado Logitech que o OpenRGB enxerga: pinta tecla por tecla pelo G HUB (sem conflito)."""
        if not self.start():
            return False
        d = self.dll
        with self.lock:
            d.LogiLedSetTargetDevice(4)   # teclados com cor por tecla (responde "ok" até com a sessão morta)
            good = False
            for name, c in zip(led_names, cols):
                k = key_of(name)
                if k and k["sc"] is not None:
                    good = bool(d.LogiLedSetLightingForKeyWithKeyName(k["sc"], *self._pct(c))) or good
                elif str(name).strip().lower() in ("logo", "g logo"):
                    good = bool(d.LogiLedSetLightingForKeyWithKeyName(0xFFFF1, *self._pct(c))) or good
            if not self._result(good):
                return False
        return good


BRIDGES = [LogitechBridge()]
try:   # Razer, SteelSeries e Corsair (beta)
    import vendors_more
    BRIDGES += [vendors_more.RazerBridge(), vendors_more.SteelSeriesBridge(), vendors_more.CorsairBridge()]
except Exception:   # nunca deixa uma ponte nova derrubar o app
    pass
# Próximas pontes (mesmo formato): Razer Chroma (REST em localhost:54235), SteelSeries GameSense
# (JSON local), Corsair iCUE SDK e ASUS Aura SDK. A IA ativa só as que existem no PC (pc.json -> "vendors").


def bridge(key):
    return next((b for b in BRIDGES if b.key == key), None)


def detect_bridges():
    """Quais pontes este PC tem (kit do fabricante instalado e programa aberto). Usado pela IA na instalação."""
    out = []
    for b in BRIDGES:
        try:
            out.append({"key": b.key, "app": b.app, "installed": bool(b.installed()), "running": bool(b.available())})
        except Exception as e:
            out.append({"key": b.key, "app": b.app, "installed": False, "running": False, "error": str(e)})
    return out
