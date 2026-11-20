"""Pontes com Razer Synapse (Chroma), SteelSeries GG (GameSense) e Corsair iCUE.

Mesma ideia da ponte Logitech (vendors.py): o EasyRGB pinta por cima do programa do fabricante usando o kit
oficial que ele oferece para jogos e aplicativos, sem desligar nem brigar com ele.

- Razer: REST local da Chroma SDK (http://localhost:54235).
- SteelSeries: GameSense (endereço local em coreProps.json).
- Corsair: iCUE SDK v4 (iCUESDK.x64_2019.dll, baixada do GitHub oficial da Corsair quando o iCUE existe).

Beta: feitas a partir da documentação oficial e testadas com servidores simulados, ainda sem o hardware real.
"""
import ctypes
import json
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

import vendors
from vendors import VirtualDevice, key_of

GRID_W, GRID_H = 22, 6


def _http(method, url, body=None, timeout=0.6):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def key_grid(led_names, cols, offset_x=0, fill=(0, 0, 0)):
    """Coloca as cores das teclas numa grade 22x6 (o formato de teclado da Razer e da SteelSeries)."""
    grid = [[fill] * GRID_W for _ in range(GRID_H)]
    for name, c in zip(led_names, cols):
        k = key_of(name)
        if not k:
            continue
        col = min(GRID_W - 1, max(0, int(round(k["x"])) + offset_x))
        row = min(GRID_H - 1, max(0, int(round(k["y"]))))
        grid[row][col] = tuple(c)
    return grid


class Bridge:
    """Base das pontes: estado de conexão e o básico que o rgb_controller usa."""
    key = app = ""
    routes_keys = True   # sabe pintar tecla por tecla um teclado que o OpenRGB enxerga
    RETRY = 3

    def __init__(self):
        self.lock = threading.RLock()
        self.ok, self.retry_at, self.fails, self.connects = False, 0.0, 0, 0
        self._last = {}

    def installed(self):
        return False

    def available(self):
        return False

    def restarted(self):
        return False

    def start(self):
        return False

    def stop(self):
        self.ok = False

    def _failed(self):
        self.fails += 1
        if self.fails >= 5:
            self.stop()

    def _changed(self, key, value, every=1.0):
        """Evita reenviar a mesma cor 20x por segundo (as pontes por HTTP têm limite)."""
        old = self._last.get(key)
        if old and old[0] == value and time.time() - old[1] < every:
            return False
        self._last[key] = (value, time.time())
        return True

    def devices(self, cfg):
        items = cfg or [{"type": "all", "zones": 1, "name": f"{self.app.split()[0]} ({self.app.split()[-1]})"}]
        out = []
        for it in items:
            t = str(it.get("type", "all")).lower()
            out.append(VirtualDevice(self, it.get("name") or f"{self.app.split()[0]} {t}",
                                     vendors.LogitechBridge.OPENRGB_TYPE.get(t, 19), [("Luz", 1)], t))
        return out

    def paint(self, dev, cols):
        pass

    def paint_keys(self, led_names, cols):
        return False


# ---------------------------------------------------------------- Razer Chroma
def bgr(c):
    return int(c[0]) | int(c[1]) << 8 | int(c[2]) << 16


class RazerBridge(Bridge):
    key, app = "razer", "Razer Synapse"
    BASE = "http://localhost:54235/razer/chromasdk"
    TARGETS = {"keyboard": "keyboard", "mouse": "mouse", "headset": "headset", "mousemat": "mousepad",
               "keypad": "keypad", "speaker": "chromalink"}

    def __init__(self):
        super().__init__()
        self.uri, self.beat = None, 0.0
        self._seen = (0.0, False)

    def available(self):
        if time.time() - self._seen[0] < 10:
            return self._seen[1]
        try:
            _http("GET", self.BASE, timeout=0.4)
            ok = True
        except Exception:
            ok = False
        self._seen = (time.time(), ok)
        return ok

    installed = available

    def start(self):
        with self.lock:
            if self.ok:
                if time.time() - self.beat > 8:   # a Chroma encerra a sessão sem sinal de vida em ~15 s
                    try:
                        _http("PUT", f"{self.uri}/heartbeat", timeout=1)
                        self.beat = time.time()
                    except Exception:
                        self.stop()
                return self.ok
            if time.time() < self.retry_at:
                return False
            self.retry_at = time.time() + self.RETRY
            try:
                j = _http("POST", self.BASE, {
                    "title": "EasyRGB", "description": "RGB controller for the whole PC",
                    "author": {"name": "EasyRGB", "contact": "https://github.com/lucianookdp/EasyRGB"},
                    "device_supported": sorted(set(self.TARGETS.values())), "category": "application"}, timeout=3)
                self.uri = j["uri"]
            except Exception:
                return False
            time.sleep(1.0)   # a sessão nova leva um instante para aceitar comandos
            self.ok, self.fails, self.beat = True, 0, time.time()
            self.connects += 1
            return True

    def stop(self):
        with self.lock:
            if self.ok and self.uri:
                try:
                    _http("DELETE", self.uri, timeout=1)
                except Exception:
                    pass
            self.ok, self.uri = False, None

    def _put(self, target, body):
        try:
            _http("PUT", f"{self.uri}/{target}", body)
            self.fails, self.beat = 0, time.time()
            return True
        except Exception:
            self._failed()
            return False

    def paint(self, dev, cols):
        if not cols or not self.start():
            return
        targets = list(self.TARGETS.values()) if dev.target not in self.TARGETS else [self.TARGETS[dev.target]]
        color = bgr(cols[0])
        for t in targets:
            if self._changed(t, color):
                self._put(t, {"effect": "CHROMA_STATIC", "param": {"color": color}})

    def paint_keys(self, led_names, cols):
        if not self.start():
            return False
        grid = [[bgr(c) for c in row] for row in key_grid(led_names, cols, offset_x=1)]
        return self._put("keyboard", {"effect": "CHROMA_CUSTOM", "param": grid})


# ---------------------------------------------------------------- SteelSeries GameSense
class SteelSeriesBridge(Bridge):
    key, app = "steelseries", "SteelSeries GG"
    GAME, EVENT = "EASYRGB", "LIGHTS"

    def __init__(self):
        super().__init__()
        self.addr, self.value, self.beat = None, 0, 0.0
        self.frame = {"bitmap": [[0, 0, 0]] * (GRID_W * GRID_H), "c1": [0, 0, 0], "c2": [0, 0, 0]}

    @staticmethod
    def props():
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SteelSeries" / "SteelSeries Engine 3" / "coreProps.json"

    def installed(self):
        return self.props().exists()

    def _address(self):
        try:
            return json.loads(self.props().read_text(encoding="utf-8"))["address"]
        except Exception:
            return None

    def available(self):
        addr = self._address()
        if not addr:
            return False
        host, _, port = addr.partition(":")
        try:
            with socket.create_connection((host, int(port)), timeout=0.3):
                return True
        except Exception:
            return False

    def _post(self, path, body, timeout=0.6):
        return _http("POST", f"http://{self.addr}/{path}", body, timeout=timeout)

    def start(self):
        with self.lock:
            if self.ok:
                if time.time() - self.beat > 10:
                    try:
                        self._post("game_heartbeat", {"game": self.GAME})
                        self.beat = time.time()
                    except Exception:
                        self.stop()
                return self.ok
            if time.time() < self.retry_at:
                return False
            self.retry_at = time.time() + self.RETRY
            self.addr = self._address()
            if not self.addr:
                return False
            color = lambda k: {"device-type": k[0], "zone": k[1], "mode": "context-color",  # noqa: E731
                               "context-frame-key": k[2]}
            try:
                self._post("game_metadata", {"game": self.GAME, "game_display_name": "EasyRGB",
                                             "developer": "EasyRGB", "deinitialize_timer_length_ms": 60000}, 3)
                self._post("bind_game_event", {"game": self.GAME, "event": self.EVENT, "value_optional": True,
                                               "handlers": [{"device-type": "rgb-per-key-zones", "mode": "bitmap"},
                                                            color(("rgb-1-zone", "one", "c1")),
                                                            color(("rgb-2-zone", "one", "c1")),
                                                            color(("rgb-2-zone", "two", "c2"))]}, 3)
            except Exception:
                return False
            self.ok, self.fails, self.beat = True, 0, time.time()
            self.connects += 1
            return True

    def stop(self):
        with self.lock:
            if self.ok and self.addr:
                try:
                    self._post("stop_game", {"game": self.GAME}, 1)
                except Exception:
                    pass
            self.ok = False

    def _send(self):
        self.value = (self.value + 1) % 100   # o GameSense só repinta quando o valor muda
        try:
            self._post("game_event", {"game": self.GAME, "event": self.EVENT,
                                      "data": {"value": self.value, "frame": self.frame}})
            self.fails, self.beat = 0, time.time()
            return True
        except Exception:
            self._failed()
            return False

    @staticmethod
    def _rgb(c):
        return {"red": int(c[0]), "green": int(c[1]), "blue": int(c[2])}

    def paint(self, dev, cols):
        if not cols or not self.start():
            return
        c1, c2 = cols[0], cols[-1]
        if not self._changed(("zones", dev.target), (tuple(c1), tuple(c2))):
            return
        self.frame["c1"], self.frame["c2"] = self._rgb(c1), self._rgb(c2)
        if dev.target in ("all", "keyboard"):
            self.frame["bitmap"] = [list(c1)] * (GRID_W * GRID_H)
        self._send()

    def paint_keys(self, led_names, cols):
        if not self.start():
            return False
        self.frame["bitmap"] = [list(c) for row in key_grid(led_names, cols) for c in row]
        return self._send()


# ---------------------------------------------------------------- Corsair iCUE SDK v4
class _CVersion(ctypes.Structure):
    _fields_ = [("major", ctypes.c_int), ("minor", ctypes.c_int), ("patch", ctypes.c_int)]


class _CSessionDetails(ctypes.Structure):
    _fields_ = [("clientVersion", _CVersion), ("serverVersion", _CVersion), ("serverHostVersion", _CVersion)]


class _CSessionStateChanged(ctypes.Structure):
    _fields_ = [("state", ctypes.c_int), ("details", _CSessionDetails)]


class _CDeviceFilter(ctypes.Structure):
    _fields_ = [("deviceTypeMask", ctypes.c_int)]


class _CDeviceInfo(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("id", ctypes.c_char * 128), ("serial", ctypes.c_char * 128),
                ("model", ctypes.c_char * 128), ("ledCount", ctypes.c_int), ("channelCount", ctypes.c_int)]


class _CLedPosition(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint), ("cx", ctypes.c_double), ("cy", ctypes.c_double)]


class _CLedColor(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint), ("r", ctypes.c_ubyte), ("g", ctypes.c_ubyte), ("b", ctypes.c_ubyte),
                ("a", ctypes.c_ubyte)]


_STATE_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(_CSessionStateChanged))
CORSAIR_TYPES = {0x1: 5, 0x2: 6, 0x4: 7, 0x8: 8, 0x10: 9, 0x20: 3, 0x40: 4, 0x80: 1, 0x100: 3, 0x200: 0, 0x400: 2}
CONNECTED, DEVICE_ALL, EXCLUSIVE_LIGHTING = 6, -1, 1   # CSS_Connected, CDT_All (0xFFFFFFFF), CAL_ExclusiveLightingControl


class CorsairBridge(Bridge):
    key, app = "corsair", "Corsair iCUE"
    routes_keys = False   # os aparelhos Corsair entram como dispositivos próprios, com a posição real de cada LED
    DLL = "iCUESDK.x64_2019.dll"

    def __init__(self):
        super().__init__()
        self.dll, self.state, self.devs = None, 0, []
        self._cb = _STATE_CB(self._on_state)

    @staticmethod
    def sdk_dir():
        base = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        data = Path(sys.executable).resolve().parent / "app" if getattr(sys, "frozen", False) else base
        return data / "lib" / "corsair"

    def dll_path(self):
        cands = [self.sdk_dir() / self.DLL]
        for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
            if pf:
                cands += list(Path(pf, "Corsair").glob(f"*iCUE*/{self.DLL}"))
        return next((p for p in cands if p.exists()), None)

    def installed(self):
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"), "Corsair")
        return pf.exists() and any(pf.glob("*iCUE*"))

    def available(self):
        return self.dll_path() is not None and vendors._running("iCUE.exe")

    def _on_state(self, _ctx, ev):
        try:
            self.state = ev.contents.state
        except Exception:
            pass

    def start(self):
        with self.lock:
            if self.ok:
                if self.state != CONNECTED:
                    self.stop()
                return self.ok
            if time.time() < self.retry_at:
                return False
            self.retry_at = time.time() + self.RETRY
            p = self.dll_path()
            if not p:
                return False
            try:
                d = self.dll or ctypes.CDLL(str(p))
                self.dll = d
                d.CorsairConnect(self._cb, None)
                for _ in range(30):   # o iCUE responde pelo callback
                    if self.state == CONNECTED:
                        break
                    time.sleep(0.1)
                if self.state != CONNECTED:
                    return False
                self.devs = self._list()
            except Exception:
                return False
            self.ok, self.fails = True, 0
            self.connects += 1
            return True

    def _list(self):
        d = self.dll
        arr = (_CDeviceInfo * 64)()
        n = ctypes.c_int(0)
        flt = _CDeviceFilter(DEVICE_ALL)
        d.CorsairGetDevices(ctypes.byref(flt), 64, arr, ctypes.byref(n))
        out = []
        for info in arr[: n.value]:
            if info.ledCount <= 0:
                continue
            pos = (_CLedPosition * 512)()
            m = ctypes.c_int(0)
            d.CorsairGetLedPositions(info.id, 512, pos, ctypes.byref(m))
            leds = [(p.id, p.cx, p.cy) for p in pos[: m.value]]
            d.CorsairRequestControl(info.id, EXCLUSIVE_LIGHTING)
            out.append({"id": bytes(info.id), "type": info.type, "model": info.model.decode(errors="ignore").strip(),
                        "leds": leds})
        return out

    def stop(self):
        with self.lock:
            if self.ok and self.dll:
                try:
                    self.dll.CorsairDisconnect()
                except Exception:
                    pass
            self.ok, self.state = False, 0

    def devices(self, cfg):
        if not self.start():
            return []
        out = []
        for dv in self.devs:
            xs = [l[1] for l in dv["leds"]] or [0]
            ys = [l[2] for l in dv["leds"]] or [0]
            w, h = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1
            typ = next((v for k, v in CORSAIR_TYPES.items() if dv["type"] & k), 19)
            vd = VirtualDevice(self, dv["model"] or "Corsair", typ, [("LEDs", len(dv["leds"]))], dv["id"])
            vd.positions = [((x - min(xs)) / w, (y - min(ys)) / h) for _, x, y in dv["leds"]]
            vd.led_ids = [l[0] for l in dv["leds"]]
            out.append(vd)
        return out

    def paint(self, dev, cols):
        if not cols or not self.start():
            return
        ids = getattr(dev, "led_ids", [])
        arr = (_CLedColor * len(ids))(*[_CLedColor(i, c[0], c[1], c[2], 255) for i, c in zip(ids, cols)])
        try:
            self.dll.CorsairSetLedColors(dev.target, len(ids), arr)
            self.fails = 0
        except Exception:
            self._failed()


def download_corsair_sdk(target=None):
    """Baixa a iCUESDK.x64_2019.dll do repositório oficial da Corsair (só se o iCUE estiver instalado)."""
    import io
    import zipfile
    b = CorsairBridge()
    target = Path(target or b.sdk_dir())
    if (target / b.DLL).exists():
        return target / b.DLL
    req = urllib.request.Request("https://api.github.com/repos/CorsairOfficial/cue-sdk/releases/latest",
                                 headers={"User-Agent": "EasyRGB", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        rel = json.loads(r.read())
    url = next(a["browser_download_url"] for a in rel.get("assets", []) if a["name"].lower().endswith(".zip"))
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "EasyRGB"}), timeout=120) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    name = next(n for n in z.namelist() if n.replace("\\", "/").lower().endswith("x64/" + b.DLL.lower()))
    target.mkdir(parents=True, exist_ok=True)
    (target / b.DLL).write_bytes(z.read(name))
    return target / b.DLL
