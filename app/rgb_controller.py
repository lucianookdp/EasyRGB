"""EasyRGB v1 - controlador RGB por paletas, em cima do OpenRGB (servidor SDK na porta 6742).

Uso:
  python rgb_controller.py                 -> abre a interface no navegador
  python rgb_controller.py aplicar gta6    -> aplica um preset (busca por parte do nome)
  python rgb_controller.py aplicar "#FF2E88 #9B3DFF 00D9C8" [--brilho 80] [--modo gradiente|alternado|zona] [--gravar]
  python rgb_controller.py ia perfil.json   (ou JSON pelo stdin com "-") -> perfil de cores feito por um agente de IA
  python rgb_controller.py listar          -> mostra dispositivos, zonas e efeitos do chip
  python rgb_controller.py detectar        -> relatório JSON do PC para um agente de IA configurar tudo
  python rgb_controller.py configurar pc.json   (ou "-") -> salva o perfil do PC feito pelo agente
  python rgb_controller.py conectar        -> abre o OpenRGB (servidor SDK)
  python rgb_controller.py automacao [regras.json | -]  -> mostra ou salva jogos e horários automáticos
  python rgb_controller.py jogos           -> jogos conhecidos instalados (Steam, Epic, Riot...)
  python rgb_controller.py iniciar-com-windows [sim|nao]
  python rgb_controller.py compartilhar    -> código EASYRGB1-... do visual atual
  python rgb_controller.py importar EASYRGB1-...
  python rgb_controller.py desligar
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Dois jeitos de rodar: pelo código (python app/rgb_controller.py) ou empacotado (EasyRGB.exe, sem precisar de Python).
FROZEN = bool(getattr(sys, "frozen", False))
SRC = Path(__file__).resolve().parent
# HERE = dados que mudam (estado, perfil do PC, presets do usuário, log); RES = arquivos que vêm com o app.
HERE = Path(sys.executable).resolve().parent / "app" if FROZEN else SRC
RES = Path(getattr(sys, "_MEIPASS", SRC))
ROOT = HERE.parent   # pasta do EasyRGB (OpenRGB, instalador, configurado.ok)
if FROZEN:
    HERE.mkdir(exist_ok=True)
sys.path.insert(0, str(SRC))
import vendors  # noqa: E402  (pontes com G HUB e outros programas de fabricante)
# Bibliotecas ficam dentro do app, separadas por versão do Python (Pillow e outras têm partes compiladas:
# as de um Python não servem em outro). Se o Python do PC mudar, o app instala de novo sozinho.
LIB = HERE / "lib" / f"py{sys.version_info[0]}{sys.version_info[1]}"
REQUIREMENTS = ["openrgb-python", "pycaw", "comtypes", "pystray", "pillow"]
sys.path.insert(0, str(HERE / "lib"))   # pasta antiga: só as bibliotecas sem partes compiladas servem
sys.path.insert(0, str(LIB))


def ensure_libs():
    """Instala as bibliotecas para o Python atual, uma vez (usa a internet só nessa hora)."""
    if FROZEN or (LIB / ".ok").exists():   # o EasyRGB.exe já vem com tudo
        return True
    py = Path(sys.executable).with_name("python.exe")
    exe = py if py.exists() else Path(sys.executable)
    try:
        r = subprocess.run([str(exe), "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade",
                            "--target", str(LIB), *REQUIREMENTS], capture_output=True, text=True, timeout=900,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        print("Não consegui instalar as bibliotecas:", e)
        return False
    if r.returncode == 0:
        (LIB / ".ok").write_text(sys.version, encoding="utf-8")
        import importlib
        importlib.invalidate_caches()
        return True
    print("pip falhou:", (r.stderr or r.stdout)[-800:])
    return False


PALETTES_FILE = RES / "palettes.json"
STATE_FILE = HERE / "last_state.json"
CLAUDE_FILE = HERE / "claude_color.json"
OPENRGB_EXE = ROOT / "OpenRGB" / "OpenRGB Windows 64-bit" / "OpenRGB.exe"
APP_NAME = "EasyRGB"
REPO = "lucianookdp/EasyRGB"   # de onde vêm as atualizações (GitHub Releases)
VERSION = "1.2.1"
UI_PORT = 6750
SDK_PORT = 6742

_lock = threading.RLock()
_client = None
_effect = {"thread": None, "stop": threading.Event(), "on": False}


# ---------------------------------------------------------------- cores
def parse_colors(text):
    """Aceita '#FF00AA', 'ff00aa', '#f0a', 'rgb(255,0,170)', separados por espaço, vírgula, ; ou linhas."""
    if isinstance(text, list):
        text = " ".join(str(t) for t in text)
    out = []
    pat = r"rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)|#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b|\b([0-9a-fA-F]{6})\b"
    for m in re.finditer(pat, text or "", re.I):
        if m.group(1):
            out.append(tuple(min(255, int(m.group(i))) for i in (1, 2, 3)))
            continue
        h = m.group(4) or m.group(5)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        out.append(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
    return out


def to_hex(c):
    return "#%02X%02X%02X" % tuple(c)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(colors, n, offset=0.0):
    """n cores ao longo da paleta. offset (0..1) desloca em círculo, para o efeito 'fluir'."""
    if n <= 0:
        return []
    if len(colors) == 1:
        return [colors[0]] * n
    if offset:
        ring, segs = colors + [colors[0]], len(colors)
        pos = [((i / n) + offset) % 1.0 for i in range(n)]
    else:
        ring, segs = colors, len(colors) - 1
        pos = [i / max(1, n - 1) for i in range(n)]
    res = []
    for p in pos:
        x = p * segs
        k = min(int(x), segs - 1)
        res.append(lerp(ring[k], ring[k + 1], x - k))
    return res


def scale(c, brightness):
    f = max(0, min(100, brightness)) / 100.0
    return tuple(round(v * f) for v in c)


def zone_colors(n, zi, palette, mode, offset=0.0):
    """Cores de uma zona com n LEDs (zi = posição da zona, usada no modo 'uma cor por zona')."""
    if n <= 0:
        return []
    if mode == "zona" or n == 1:
        k = int(offset * len(palette)) if offset else 0
        return [palette[(zi + k) % len(palette)]] * n
    if mode == "alternado":
        k = int(offset * len(palette)) if offset else 0
        return [palette[(i + k) % len(palette)] for i in range(n)]
    return gradient(palette, n, offset)


def colors_for_device(dev, palette, mode, offset=0.0, zone_over=None):
    """zone_over: {"<índice da zona>": "#RRGGBB"} -> zona inteira numa cor escolhida à mão."""
    zone_over = zone_over or {}
    out = []
    for zi, zone in enumerate(dev.zones):
        fixed = parse_colors(zone_over.get(str(zi), ""))
        n = len(zone.leds)
        out += [fixed[0]] * n if fixed else zone_colors(n, zi, palette, mode, offset)
    return out


def plan_colors(devs, ids, palette, mode, offset, overrides, groups):
    """Calcula as cores de cada dispositivo.
    groups: [{"ids": [1, 2], "mode": "mirror" | "span"}]
      mirror = os dispositivos do grupo ficam iguais (o primeiro manda nas cores fixas por zona)
      span   = o grupo vira uma fita só: o gradiente atravessa todos os módulos em sequência
    """
    overrides = dict(overrides or {})
    result, done = {}, set()
    for g in groups or []:
        members = [i for i in g.get("ids", []) if i in ids and i < len(devs)]
        if len(members) < 2:
            continue
        lead = overrides.get(str(members[0]))
        for i in members[1:]:  # cores fixas por zona sempre iguais dentro de um grupo
            if lead:
                overrides[str(i)] = dict(lead)
            else:
                overrides.pop(str(i), None)
        if g.get("mode") != "span":
            continue
        per = {i: [] for i in members}
        for zi in range(max(len(devs[i].zones) for i in members)):
            segs = [(i, len(devs[i].zones[zi].leds)) for i in members if zi < len(devs[i].zones)]
            base = zone_colors(sum(n for _, n in segs), zi, palette, mode, offset)
            pos = 0
            for i, n in segs:
                fixed = parse_colors((overrides.get(str(i)) or {}).get(str(zi), ""))
                per[i] += [fixed[0]] * n if fixed else base[pos:pos + n]
                pos += n
        result.update(per)
        done.update(members)
    for i in ids:
        if i not in done and i < len(devs):
            result[i] = colors_for_device(devs[i], palette, mode, offset, overrides.get(str(i)))
    # cor por tecla/LED ("L<índice>"), usada nas teclas em destaque do teclado
    for i, cols in result.items():
        for k, v in (overrides.get(str(i)) or {}).items():
            if str(k).startswith("L") and str(k)[1:].isdigit() and int(str(k)[1:]) < len(cols):
                c = parse_colors(v)
                if c:
                    cols[int(str(k)[1:])] = c[0]
    return result


# ---------------------------------------------------------------- OpenRGB
def openrgb_running():
    import socket
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", SDK_PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def start_openrgb():
    """Abre o OpenRGB minimizado com o servidor SDK (como admin, para acessar o chip RGB da placa)."""
    if openrgb_running():
        return True
    if not OPENRGB_EXE.exists():
        raise RuntimeError(f"OpenRGB não encontrado em {OPENRGB_EXE}. Rode o instalador primeiro.")
    # só "--server": o OpenRGB roda como servidor invisível, sem janela e sem ícone próprio na bandeja
    # (o ícone que aparece é só o do EasyRGB). "--startminimized" criaria um segundo ícone.
    args = "--server --noautoconnect"
    ps = (f"Start-Process -FilePath '{OPENRGB_EXE}' -ArgumentList '{args}' -Verb RunAs -WindowStyle Hidden "
          f"-WorkingDirectory '{OPENRGB_EXE.parent}'")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
    for _ in range(60):  # a detecção de hardware leva alguns segundos
        if openrgb_running():
            time.sleep(1.5)
            return True
        time.sleep(0.5)
    return False


def client(refresh=False, autostart=True):
    """Conexão com o OpenRGB. refresh=True relê a lista de dispositivos (mais lento)."""
    global _client
    with _lock:
        if _client is not None:
            if not refresh:
                return _client
            try:
                _client.update()
                return _client
            except Exception:
                _client = None
        if not openrgb_running():
            if not autostart or not start_openrgb():
                raise RuntimeError("OpenRGB não está rodando (servidor SDK na porta 6742).")
        from openrgb import OpenRGBClient
        last = None
        for _ in range(10):
            try:
                _client = OpenRGBClient("127.0.0.1", SDK_PORT, APP_NAME)
                return _client
            except Exception as e:  # servidor ainda subindo
                last = e
                time.sleep(1)
        raise RuntimeError(f"Não consegui conectar ao OpenRGB: {last}")


_vend = {"t": 0.0, "devs": [], "keys": [], "sig": None}


def vendor_devices(openrgb_devs=()):
    """Dispositivos controlados por cima do programa do fabricante (G HUB...). Só entra o que existe neste PC
    e não foi desligado pela IA no pc.json ("vendors": {"logitech": {"enabled": false}})."""
    if os.environ.get("EASYRGB_NO_VENDORS"):
        return []
    cfg = (load_pc() or {}).get("vendors") or {}
    has = {b.key: any(b.key in _maker(d) for d in openrgb_devs) for b in vendors.BRIDGES}
    sig = json.dumps([cfg, has], sort_keys=True)
    if time.time() - _vend["t"] < 15 and sig == _vend["sig"]:
        return _vend["devs"]
    devs, keys = [], []
    for b in vendors.BRIDGES:
        c = cfg.get(b.key) or {}
        try:
            ok = c.get("enabled", True) is not False and b.available()
        except Exception:
            ok = False
        if not ok:
            if b.key in _vend["keys"]:
                b.stop()   # devolve as luzes ao programa do fabricante
            continue
        keys.append(b.key)
        old = [d for d in _vend["devs"] if d.backend == b.key]
        if old and sig == _vend["sig"]:
            devs += old
        elif c.get("devices") or not has[b.key]:   # sem config e já visto pelo OpenRGB: não duplica
            devs += b.devices(c.get("devices"))
    _vend.update(t=time.time(), devs=devs, keys=keys, sig=sig)
    return devs


def _maker(dev):
    """Nome + fabricante do dispositivo (o OpenRGB chama o G PRO de "PRO Gaming Keyboard", mas sabe que é Logitech)."""
    meta = getattr(dev, "metadata", None)
    return f"{getattr(dev, 'name', '')} {getattr(meta, 'vendor', '') or ''}".lower()


def all_devices(c):
    """Dispositivos do OpenRGB + os controlados por cima do programa do fabricante (ids depois dos do OpenRGB)."""
    return list(c.devices) + vendor_devices(c.devices)


def vendor_route(dev):
    """Ponte que deve pintar um dispositivo do OpenRGB (ex.: teclado Logitech com o G HUB aberto)."""
    if isinstance(dev, vendors.VirtualDevice):
        return None
    name = _maker(dev)
    return next((b for b in vendors.BRIDGES if b.key in _vend["keys"] and b.key in name
                 and getattr(b, "routes_keys", True)), None)


def reset_client():
    global _client
    with _lock:
        _client = None


def prepare_device(dev):
    names = [m.name.lower() for m in dev.modes]
    for wanted in ("direct", "static", "custom"):
        if wanted in names:
            if dev.modes[dev.active_mode].name.lower() != wanted:
                try:
                    dev.set_mode(wanted)
                except Exception:
                    continue
            return wanted
    return None


def dev_type(d):
    """Nome do tipo do dispositivo (MOTHERBOARD, DRAM, KEYBOARD...)."""
    try:
        from openrgb.utils import DeviceType
        return DeviceType(int(d.type)).name
    except Exception:
        return getattr(d.type, "name", str(d.type))


# ---------------------------------------------------------------- efeitos nativos do hardware
# Cada placa/RAM/teclado tem seus próprios efeitos gravados no chip (lidos do OpenRGB, então funciona
# com qualquer hardware suportado). Eles rodam sozinhos, mesmo com o EasyRGB fechado.
_HW_SKIP = {"direct", "static", "off", "custom", "argb header config", "music"}
_HW_FLAG_SPEED, _HW_PER_LED, _HW_MODE_COLOR = 1, 1, 2   # flag HAS_SPEED; color_mode PER_LED / MODE_SPECIFIC
_hw_cache = {}   # id -> (modo, velocidade) já enviados, para não reenviar o modo a cada mudança de cor


def hw_effects(dev):
    out = []
    for m in dev.modes:
        if m.name.lower() in _HW_SKIP:
            continue
        cm = int(m.color_mode or 0)
        out.append({"name": m.name,
                    "speed": bool(int(m.flags or 0) & _HW_FLAG_SPEED) and m.speed_min is not None,
                    "colors": "led" if cm == _HW_PER_LED else "mode" if cm == _HW_MODE_COLOR else "none"})
    return out


def apply_hw(idx, dev, name, speed_pct, led_colors, palette, save, RGBColor):
    m = next((x for x in dev.modes if x.name.lower() == str(name).lower()), None)
    if m is None:
        raise ValueError(f"Efeito {name!r} não existe em {dev.name}")
    cm = int(m.color_mode or 0)
    key = (m.name, int(speed_pct))
    if cm == _HW_MODE_COLOR:
        n = max(m.colors_min or 1, min(m.colors_max or 1, len(palette)))
        m.colors = [RGBColor(*palette[i % len(palette)]) for i in range(n)]
        key += tuple(palette[:n])
    if int(m.flags or 0) & _HW_FLAG_SPEED and m.speed_min is not None:
        m.speed = round(m.speed_min + (m.speed_max - m.speed_min) * max(0, min(100, speed_pct)) / 100)
    if save or _hw_cache.get(idx) != key or dev.modes[dev.active_mode].name != m.name:
        import warnings
        with warnings.catch_warnings():  # alguns teclados não "confirmam" o modo, mas aplicam normalmente
            warnings.simplefilter("ignore")
            dev.set_mode(m, save=save)
        _hw_cache[idx] = key
    if cm == _HW_PER_LED and led_colors:
        dev.set_colors([RGBColor(*c) for c in led_colors])


_MANUAL_SAVE, _AUTO_SAVE = 256, 512


def persist_kind(dev):
    """O que o chip guarda quando o PC desliga: 'auto' (guarda sozinho), 'manual' (só cor fixa, ao gravar)
    ou 'none' (perde a cor; precisa do EasyRGB ao ligar o PC)."""
    if getattr(dev, "persist", None) or vendor_route(dev):
        return "vendor"   # o programa do fabricante volta ao perfil dele quando o EasyRGB fecha
    flags = [int(m.flags or 0) for m in dev.modes if m.name.lower() in ("direct", "static")]
    if any(f & _AUTO_SAVE for f in flags):
        return "auto"
    if any(f & _MANUAL_SAVE for f in flags):
        return "manual"
    return "none"


def _vendor_name(d):
    """Marca do dispositivo (o OpenRGB sabe; nos aparelhos das pontes é a marca da ponte)."""
    if isinstance(d, vendors.VirtualDevice):
        return d.bridge.app.split()[0]
    return str(getattr(getattr(d, "metadata", None), "vendor", "") or "").strip()


def device_info():
    c = client(refresh=True, autostart=False)
    return [{"id": i, "name": d.name, "type": dev_type(d),
             "backend": getattr(d, "backend", None) or (vendor_route(d).key if vendor_route(d) else "openrgb"),
             "effects": [] if vendor_route(d) or isinstance(d, vendors.VirtualDevice) else hw_effects(d),
             "persist": persist_kind(d), "vendor": _vendor_name(d),
             "zones": [{"name": z.name, "leds": len(z.leds)} for z in d.zones],
             **({"led_names": [getattr(l, "name", "") for l in getattr(d, "leds", None) or []]}
                if dev_type(d) == "KEYBOARD" else {})}
            for i, d in enumerate(all_devices(c))]


_sent = {}   # último quadro enviado a cada aparelho (efeitos animados)


def apply(palette, brightness=100, mode="gradiente", devices=None, save=False, offset=0.0, fast=False,
          overrides=None, groups=None, persist=True, ui=None, hw=None, frame=None, dev_bri=None):
    """Envia as cores para o hardware.
    devices: ids incluídos (None = todos) | overrides: {"<id>": {"<zona>": "#RRGGBB"}}
    hw: {"<id>": {"mode": "Breathing", "speed": 0-100}} -> efeito nativo do chip nesse dispositivo
    persist=False: só pré-visualização (não grava o estado salvo do app).
    frame: função (id, dispositivo, cores) -> cores, usada pelos efeitos que pintam LED por LED (onda...)."""
    if not palette:
        raise ValueError("Paleta vazia")
    from openrgb.utils import RGBColor
    hw = {str(k): v for k, v in (hw or {}).items() if v and v.get("mode")}
    # brilho próprio de um aparelho (ex.: teclado em 60%), multiplicado pelo brilho geral
    dev_bri = {str(k): v for k, v in (dev_bri if dev_bri is not None else (ui or {}).get("pbri") or {}).items()}
    for attempt in (1, 2):
        try:
            c = client()
            devs = all_devices(c)
            ids = [i for i in range(len(devs)) if devices is None or i in devices]
            plan = plan_colors(devs, ids, palette, mode, offset, overrides, groups)
            report = []
            with _lock:
                for idx in ids:
                    dev, cols = devs[idx], plan.get(idx) or []
                    if not cols:
                        continue
                    bri = brightness * max(0, min(100, float(dev_bri.get(str(idx), 100)))) / 100
                    if frame:
                        cols = frame(idx, dev, cols)
                        sig = (round(bri), tuple(cols))
                        if _sent.get(idx) == sig:   # nada mudou neste aparelho: não manda de novo
                            report.append({"id": idx, "device": dev.name, "leds": len(cols), "ok": True})
                            continue
                        _sent[idx] = sig
                    elif not fast:
                        _sent.pop(idx, None)
                    try:
                        vb = vendor_route(dev)
                        if vb:   # pinta por cima do programa do fabricante, sem brigar com ele
                            sc = [scale(x, bri) for x in cols]
                            if not vb.paint_keys([getattr(l, "name", "") for l in dev.leds], sc):
                                raise RuntimeError(f"{vb.app} não respondeu")
                            report.append({"id": idx, "device": dev.name, "leds": len(cols), "ok": True})
                            continue
                        if str(idx) in hw:
                            if not fast:  # efeitos animados do app não mexem em quem usa efeito do chip
                                h = hw[str(idx)]
                                apply_hw(idx, dev, h["mode"], float(h.get("speed", 50)),
                                         [scale(x, bri) for x in cols],
                                         [scale(x, bri) for x in palette], save, RGBColor)
                                report.append({"id": idx, "device": dev.name, "leds": len(cols), "ok": True})
                            continue
                        _hw_cache.pop(idx, None)
                        if not fast:
                            prepare_device(dev)
                        dev.set_colors([RGBColor(*scale(x, bri)) for x in cols], fast=fast)
                        if save:
                            try:
                                dev.save_mode()
                            except Exception:
                                pass
                        report.append({"id": idx, "device": dev.name, "leds": len(cols), "ok": True})
                    except (ConnectionError, OSError):
                        raise
                    except Exception as e:
                        report.append({"id": idx, "device": dev.name, "ok": False, "error": str(e)})
            break
        except (ConnectionError, OSError):  # OpenRGB reiniciou: reconecta e tenta de novo
            reset_client()
            if attempt == 2:
                raise
    if persist and not fast:
        STATE_FILE.write_text(json.dumps({
            "palette": [to_hex(x) for x in palette], "brightness": brightness, "mode": mode,
            "devices": devices, "overrides": overrides or {}, "groups": groups or [], "hw": hw, "ui": ui or {}},
            ensure_ascii=False), encoding="utf-8")
    return report


def turn_off():
    c = client()
    with _lock:
        for dev in all_devices(c):
            try:
                vb = vendor_route(dev)
                if vb:   # teclado pintado pelo G HUB: apaga por ele, sem brigar
                    vb.paint_keys([getattr(l, "name", "") for l in dev.leds], [(0, 0, 0)] * len(dev.leds))
                    continue
                dev.off()
            except Exception:
                pass


# ---------------------------------------------------------------- efeitos animados pelo app
# Funcionam em qualquer dispositivo, mas só enquanto o EasyRGB está aberto.
EFFECTS = ("fluir", "respirar", "ciclo", "arcoiris", "musica", "onda", "estrelas", "tela", "teclas")
SPATIAL = {"onda": 20, "estrelas": 15, "tela": 12, "teclas": 30}   # efeitos LED por LED -> quadros por segundo
WAVE_DIRS = ("direita", "esquerda", "baixo", "cima", "centro", "dentro")
RAINBOW = [(255, 0, 0), (255, 140, 0), (255, 255, 0), (0, 255, 60), (0, 200, 255), (60, 0, 255), (220, 0, 255)]


class AudioMeter:
    """Volume que está saindo nas caixas de som (0..1), lido do Windows. Leve: só um número por quadro."""

    def __init__(self):
        import comtypes
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
        comtypes.CoInitialize()
        dev = AudioUtilities.GetSpeakers()
        dev = getattr(dev, "_dev", dev)
        self._meter = cast(dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None), POINTER(IAudioMeterInformation))

    def peak(self):
        try:
            return float(self._meter.GetPeakValue())
        except Exception:
            return 0.0


def _frame(kind, palette, brightness, t, speed):
    """Paleta, brilho e deslocamento de um quadro da animação."""
    f = speed / 20.0  # velocidade 1..10 -> 0.05..0.5 voltas por segundo
    if kind == "respirar":
        import math
        return palette, brightness * (0.08 + 0.92 * (0.5 - 0.5 * math.cos(2 * math.pi * t * f * 1.5))), 0
    if kind == "ciclo":
        return gradient(palette, 1, ((t * f * 0.6) % 1.0) or 1e-6), brightness, 0
    if kind == "arcoiris":
        return RAINBOW, brightness, ((t * f) % 1.0) or 1e-6
    return palette, brightness, ((t * f) % 1.0) or 1e-6   # fluir


_pos_cache = {}


def _positions(idx, dev, n):
    k = (idx, getattr(dev, "name", ""), n)
    if k not in _pos_cache:
        pos, kb = vendors.led_positions(dev)
        if len(pos) != n:
            pos, kb = [((i + 0.5) / n, 0.5) for i in range(n)], False
        _pos_cache[k] = (pos, kb)
    return _pos_cache[k]


def _axis(x, y, d):
    return {"esquerda": 1 - x, "baixo": y, "cima": 1 - y, "centro": abs(x - 0.5) * 2,
            "dentro": 1 - abs(x - 0.5) * 2}.get(d, x)


def wave_colors(palette, pos, t, speed, direction="direita"):
    """Onda de cores com a paleta da pessoa, andando na direção escolhida (como a do G HUB)."""
    f = speed / 20.0
    return [gradient(palette, 1, ((_axis(x, y, direction) - t * f) % 1.0) or 1e-6)[0] for x, y in pos]


def star_colors(palette, pos, t, speed, state, key):
    """Estrelas: cada LED acende e apaga em seu próprio ritmo, com uma cor da paleta."""
    import math
    import random
    st = state.get(key)
    if not st or len(st) != len(pos):
        rnd = random.Random(hash(key))
        st = state[key] = [(rnd.uniform(1.2, 3.5), rnd.random(), palette[rnd.randrange(len(palette))]) for _ in pos]
    f = speed / 3.0
    out = []
    for per, ph, c in st:
        s = max(0.0, math.sin(2 * math.pi * (t * f / per + ph))) ** 6
        out.append(lerp(scale(c, 6), c, s))
    return out


def screen_shot():
    """Tela reduzida a 22x6 pontos (uma grade do tamanho de um teclado), leve de ler 12x por segundo."""
    from PIL import ImageEnhance, ImageGrab
    im = ImageGrab.grab().convert("RGB").resize((22, 6))
    return ImageEnhance.Color(im).enhance(1.6)


def screen_colors(shot, pos, kb):
    if shot is None:
        return [(0, 0, 0)] * len(pos)
    if not kb:
        return [shot.resize((1, 1)).getpixel((0, 0))] * len(pos)
    return [shot.getpixel((min(21, max(0, int(x * 22))), min(5, max(0, int(y * 6))))) for x, y in pos]


class KeyWatch:
    """Vê quais teclas acabaram de ser apertadas (só para a luz; nada é guardado nem enviado)."""

    def __init__(self):
        import ctypes
        self.get = ctypes.windll.user32.GetAsyncKeyState
        self.keys = [k for k in vendors.KEYMAP.values() if k["vk"]]
        self.down, self.hits = set(), []

    def poll(self, now):
        for k in self.keys:
            pressed = bool(self.get(k["vk"]) & 0x8000)
            if pressed and k["vk"] not in self.down:
                self.hits.append((k["x"] / vendors.KEY_W, k["y"] / vendors.KEY_H, now))
            (self.down.add if pressed else self.down.discard)(k["vk"])
        self.hits = [h for h in self.hits if now - h[2] < 1.5][-12:]


def ripple_colors(palette, pos, kb, now, speed, hits):
    """Ondulação: cada tecla apertada solta um anel de cor que se espalha pelo teclado."""
    import math
    base = scale(palette[0], 8)
    if not kb:   # mouse, RAM...: piscam junto com a digitação
        k = max([max(0.0, 1 - (now - h[2]) / 0.5) for h in hits] or [0.0])
        return [lerp(base, palette[0], k)] * len(pos)
    out = []
    for x, y in pos:
        best, col = 0.0, palette[0]
        for i, (hx, hy, ht) in enumerate(hits):
            age = now - ht
            d = math.hypot((x - hx) * vendors.KEY_W, (y - hy) * vendors.KEY_H)
            r = age * speed * 4.0
            k = max(0.0, 1 - abs(d - r) / 1.3) * max(0.0, 1 - age / 1.5)
            if k > best:
                best, col = k, palette[(i + 1) % len(palette)]
        out.append(lerp(base, col, best))
    return out


_logged = {}


def _log_once(msg, every=60):
    """Escreve um erro no log no máximo 1 vez por minuto (o efeito roda 20x por segundo)."""
    if time.time() - _logged.get(msg, 0) > every:
        _logged[msg] = time.time()
        print(time.strftime("%H:%M:%S"), msg, flush=True)


def effect_map(kind, opts, ids):
    """Efeito de cada dispositivo. kind = efeito do computador; opts["pfx"] = {"<id>": efeito} para periféricos
    (ex.: teclado com onda e PC parado). Formato antigo: opts["fxdevs"] = só esses animam."""
    pfx = {str(k): v for k, v in ((opts or {}).get("pfx") or {}).items() if v in EFFECTS or v == "static"}
    fxdevs = (opts or {}).get("fxdevs")
    out = {}
    for i in ids:
        k = pfx.get(str(i)) or (kind if not isinstance(fxdevs, list) or i in fxdevs else "static")
        out[i] = k if k in EFFECTS else "static"
    return out


def has_animation(ui):
    """Algum dispositivo anima neste visual salvo?"""
    ui = ui or {}
    return ui.get("effect") in EFFECTS or any(v in EFFECTS for v in (ui.get("pfx") or {}).values())


def effect_colors(kind, palette, cols, pos, kb, now, speed, ctx):
    """Cores de um quadro para um dispositivo, LED por LED (cada dispositivo pode ter seu próprio efeito)."""
    import math
    f = speed / 20.0
    n = len(cols)
    if kind == "respirar":
        k = 0.08 + 0.92 * (0.5 - 0.5 * math.cos(2 * math.pi * now * f * 1.5))
        return [tuple(round(v * k) for v in c) for c in cols]
    if kind == "ciclo":
        return [gradient(palette, 1, ((now * f * 0.6) % 1.0) or 1e-6)[0]] * n
    if kind == "fluir":
        return gradient(palette, n, ((now * f) % 1.0) or 1e-6)
    if kind == "arcoiris":
        return gradient(RAINBOW, n, ((now * f) % 1.0) or 1e-6)
    if kind == "musica":
        lv = 0.1 + 0.9 * ctx["level"] ** 0.7
        return [tuple(round(v * lv) for v in c) for c in gradient(palette, n, ctx["shift"] or 1e-6)]
    if kind == "onda":
        return wave_colors(palette, pos, now, speed, ctx["dir"])
    if kind == "estrelas":
        return star_colors(palette, pos, now, speed, ctx["stars"], ctx["idx"])
    if kind == "tela":
        return screen_colors(ctx["shot"], pos, kb)
    if kind == "teclas":
        return ripple_colors(palette, pos, kb, now, speed, ctx["keys"].hits if ctx["keys"] else [])
    return cols


def start_effect(palette, brightness, mode, devices, speed, overrides=None, groups=None, kind="fluir", hw=None,
                 opts=None):
    stop_effect()
    opts = opts or {}
    kind = kind if kind in EFFECTS else "static"
    ev = threading.Event()
    _effect["stop"] = ev

    pbri = opts.get("pbri") or {}
    pspd = {str(k): float(v) for k, v in (opts.get("pspd") or {}).items() if v}

    def run():
        apply(palette, brightness, mode, devices, overrides=overrides, groups=groups, persist=False, hw=hw,
              dev_bri=pbri)
        try:
            n = len(all_devices(client()))
        except Exception:
            return
        kinds = {i: k for i, k in effect_map(kind, opts, [i for i in range(n) if devices is None or i in devices]).items()
                 if k in EFFECTS}
        if not kinds:
            return   # tudo parado: a paleta já foi aplicada
        need = set(kinds.values())
        meter = None
        if "musica" in need:
            try:
                meter = AudioMeter()
            except Exception:
                meter = None
        ctx = {"level": 0.0, "shift": 0.0, "stars": {}, "keys": KeyWatch() if "teclas" in need else None,
               "dir": opts.get("dir") if opts.get("dir") in WAVE_DIRS else "direita", "shot": None, "idx": 0}
        fps = max([SPATIAL.get(k, 10) for k in need] + [20 if meter else 10])
        live, t0 = sorted(kinds), time.time()
        while not ev.is_set():
            now = time.time() - t0
            if meter:
                ctx["level"] = max(meter.peak(), ctx["level"] * 0.82)   # sobe na hora, desce suave
                ctx["shift"] = (ctx["shift"] + ctx["level"] * speed * 0.004 * 20 / fps) % 1.0
            if "tela" in need:
                try:
                    ctx["shot"] = screen_shot()
                except Exception:
                    ctx["shot"] = None
            if ctx["keys"]:
                ctx["keys"].poll(now)

            def fr(idx, dev, cols, now=now):
                pos, kb = _positions(idx, dev, len(cols))
                ctx["idx"] = idx
                return effect_colors(kinds.get(idx, "static"), palette, cols, pos, kb, now,
                                     pspd.get(str(idx), speed), ctx)
            try:
                rep = apply(palette, brightness, mode, live, fast=True, overrides=overrides, groups=groups,
                            persist=False, hw=hw, frame=fr, dev_bri=pbri)
                for r in rep:
                    if not r.get("ok"):
                        _log_once(f"efeito em {r.get('device')}: {r.get('error')}")
            except Exception as e:
                _log_once(f"efeito: {e!r}")
            ev.wait(1.0 / fps)

    th = threading.Thread(target=run, daemon=True)
    _effect.update(thread=th, on=has_animation({"effect": kind, "pfx": opts.get("pfx")}), kind=kind)
    th.start()


def stop_effect():
    _effect["stop"].set()
    th = _effect.get("thread")
    if th and th.is_alive() and th is not threading.current_thread():
        th.join(timeout=2)
    _effect.update(thread=None, on=False)


# ---------------------------------------------------------------- presets
# Dois tipos: os padrão (app/palettes.json, vêm com o app e nunca mudam) e os do usuário (app/my_presets.json).
USER_PRESETS_FILE = HERE / "my_presets.json"


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def builtin_presets():
    return _read_json(PALETTES_FILE)


def user_presets():
    return _read_json(USER_PRESETS_FILE)


def load_palettes():
    """Todos os presets: os do usuário primeiro, depois os padrão."""
    return {**user_presets(), **{k: v for k, v in builtin_presets().items() if k not in user_presets()}}


def save_user_preset(name, colors):
    name = str(name or "").strip()[:40]
    if not name:
        raise ValueError("Dê um nome ao preset")
    if name in builtin_presets():
        raise ValueError("Já existe um preset padrão com esse nome. Escolha outro.")
    cols = [to_hex(c) for c in parse_colors(colors)]
    if not cols:
        raise ValueError("Paleta vazia")
    u = user_presets()
    u[name] = cols
    USER_PRESETS_FILE.write_text(json.dumps(u, indent=2, ensure_ascii=False), encoding="utf-8")


def delete_user_preset(name):
    if name in builtin_presets() and name not in user_presets():
        raise ValueError("Os presets padrão não podem ser apagados")
    u = user_presets()
    u.pop(name, None)
    USER_PRESETS_FILE.write_text(json.dumps(u, indent=2, ensure_ascii=False), encoding="utf-8")


def find_preset(name):
    def norm(s):   # sem acento, sem espaço: "Pôr do Sol" == "por do sol"
        import unicodedata
        s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]", "", s.lower()).replace("gtavi", "gta6")
    key = norm(name or "")
    for k, v in load_palettes().items():
        if key and key in norm(k):
            return k, v
    return None, None


# ---------------------------------------------------------------- Claude Color (cores por IA)
# O usuário descreve um clima no chat com o Claude, que monta um perfil e aplica. Formato:
# {"name": "Neon Miami", "description": "...", "colors": ["#FF2E88", ...], "mode": "gradiente",
#  "brightness": 100, "save": false, "fluir": false, "speed": 3,
#  "zones":   [{"device": "teclado", "zone": "", "color": "#FFFFFF"}],  cor fixa por dispositivo/zona
#  "exclude": ["teclado"],                                              dispositivos que ficam apagados de fora
#  "links":   {"ram": "span"}}                                          separate | mirror | span
_ALIASES = {"placa": "MOTHERBOARD", "placa-mae": "MOTHERBOARD", "placa-mãe": "MOTHERBOARD",
            "motherboard": "MOTHERBOARD", "ram": "DRAM", "memoria": "DRAM", "memória": "DRAM", "dram": "DRAM",
            "teclado": "KEYBOARD", "keyboard": "KEYBOARD", "mouse": "MOUSE", "gpu": "GPU", "video": "GPU",
            "cooler": "COOLER", "fan": "COOLER", "fita": "LEDSTRIP"}


def load_claude():
    try:
        return json.loads(CLAUDE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": None, "history": []}


def _match_devices(sel, devs):
    """sel: id ('2'), apelido ('teclado', 'ram'), tipo ('KEYBOARD') ou parte do nome."""
    s = str(sel).strip().lower()
    if s.isdigit():
        return [int(s)] if int(s) < len(devs) else []
    typ = _ALIASES.get(s, s.upper())
    hit = [i for i, d in enumerate(devs) if dev_type(d) == typ]
    return hit or [i for i, d in enumerate(devs) if s in d.name.lower()]


def _match_zones(q, zones):
    """Zonas pedidas: vazio = todas; índice; nome exato; início de palavra; por último, trecho do nome.
    (Evita que "io" pegue "Audio" quando existe "IO Cover".)"""
    q = str(q or "").strip().lower()
    if not q:
        return list(range(len(zones)))
    if q.isdigit():
        return [int(q)] if int(q) < len(zones) else []
    names = [z.name.lower() for z in zones]
    for test in (lambda n: n == q, lambda n: re.search(r"\b" + re.escape(q), n), lambda n: q in n):
        hit = [i for i, n in enumerate(names) if test(n)]
        if hit:
            return hit
    return []


def resolve_profile(p, devs):
    excluded = set()
    for sel in p.get("exclude", []):
        excluded.update(_match_devices(sel, devs))
    ids = [i for i in range(len(devs)) if i not in excluded]
    overrides = {}
    for z in p.get("zones", []):
        color = parse_colors(z.get("color", ""))
        if not color:
            continue
        for di in _match_devices(z.get("device", ""), devs):
            for zi in _match_zones(z.get("zone", ""), devs[di].zones):
                overrides.setdefault(str(di), {})[str(zi)] = to_hex(color[0])
    groups, links = [], {}
    for sel, lm in (p.get("links") or {}).items():
        members = _match_devices(sel, devs)
        lm = {"juntas": "mirror", "iguais": "mirror", "continuas": "span", "contínuas": "span",
              "separadas": "separate"}.get(str(lm).lower(), str(lm).lower())
        if members:
            links[dev_type(devs[members[0]])] = lm
            if lm in ("mirror", "span") and len(members) > 1:
                groups.append({"ids": members, "mode": lm})
    hw = {}
    for h in p.get("hw", []):  # efeitos nativos: [{"device": "ram", "mode": "Chase", "speed": 60}]
        for di in _match_devices(h.get("device", ""), devs):
            if any(m.name.lower() == str(h.get("mode", "")).lower() for m in devs[di].modes):
                name = next(m.name for m in devs[di].modes if m.name.lower() == str(h["mode"]).lower())
                hw[str(di)] = {"mode": name, "speed": int(h.get("speed", 50))}
    return ids, overrides, groups, links, hw


def _pfx_from_profile(p, ids):
    """IA: "peripheral_effects": {"teclado": "onda"} -> efeito só nesse periférico."""
    out = {}
    try:
        devs = all_devices(client())
    except Exception:
        return out
    for sel, k in (p.get("peripheral_effects") or {}).items():
        for di in _match_devices(sel, devs):
            out[str(di)] = k
    return out


def apply_claude(p, allow_effect=True):
    pal = parse_colors(p.get("colors", []))
    if not pal:
        raise ValueError("Perfil de IA sem cores")
    devs = all_devices(client(refresh=True))
    ids, overrides, groups, links, hw = resolve_profile(p, devs)
    stop_effect()
    bri, mode = int(p.get("brightness", 100)), p.get("mode", "gradiente")
    kind = p.get("effect") or ("fluir" if p.get("fluir") else "static")
    speed = float(p.get("speed", 3))
    rep = apply(pal, bri, mode, ids, bool(p.get("save")), overrides=overrides, groups=groups, hw=hw,
                ui={"links": links, "effect": kind, "speed": speed, "dir": p.get("direction"),
                    "pfx": _pfx_from_profile(p, ids)})
    if allow_effect and (kind in EFFECTS or p.get("peripheral_effects")):
        start_effect(pal, bri, mode, ids, speed, overrides, groups, kind, hw, {"dir": p.get("direction"),
                                                                              "fxdevs": p.get("effect_devices"),
                                                                              "pfx": _pfx_from_profile(p, ids)})
    prof = dict(p, colors=[to_hex(c) for c in pal], created=time.strftime("%Y-%m-%d %H:%M:%S"))
    data = load_claude()
    hist = [h for h in data.get("history", []) if h.get("name") != prof.get("name")]
    CLAUDE_FILE.write_text(json.dumps({"active": prof, "history": ([prof] + hist)[:20]}, indent=2,
                                      ensure_ascii=False), encoding="utf-8")
    return rep, prof


# ---------------------------------------------------------------- detecção do PC (para agentes de IA)
PC_FILE = HERE / "pc.json"   # perfil do PC escrito pelo agente de IA depois de detectar o hardware
_RGB_SOFTWARE = {  # programas RGB de fabricantes que disputam o controle dos LEDs com o OpenRGB
    "ASRock Polychrome RGB": r"polychrome|asrrgb",
    "ASUS Armoury Crate / Aura": r"armoury|aura|lightingservice|asus.*light",
    "MSI Center / Mystic Light": r"mystic|msi.?center|msi\.central|msi_center",
    "Gigabyte RGB Fusion / Control Center": r"rgb.?fusion|gigabyte control|\bgcc\b|gigabyte.*rgb",
    "Corsair iCUE": r"icue|corsair",
    "NZXT CAM": r"nzxt",
    "Razer Synapse / Chroma": r"razer",
    "Logitech G HUB": r"lghub|g hub",
    "SteelSeries GG": r"steelseries",
    "SignalRGB": r"signalrgb|signal rgb",
    "HyperX NGENUITY": r"ngenuity",
    "Thermaltake TT RGB": r"tt ?rgb|thermaltake",
    "Lian Li L-Connect": r"l-connect|lian ?li",
    "Cooler Master MasterPlus": r"masterplus|cooler ?master",
    "G.Skill Lighting Control": r"trident z lighting|g\.?skill",
    "Kingston FURY CTRL": r"fury ?ctrl|kingston",
    "Wallpaper Engine (RGB)": r"wallpaper ?engine",
}
_DETECT_PS = r"""
$ErrorActionPreference='SilentlyContinue'
$o=[ordered]@{}
$o.motherboard = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product,Version
$o.bios = Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion,ReleaseDate
$o.cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
$o.ram = @(Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer,PartNumber,Capacity,Speed,DeviceLocator)
$o.gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion)
$o.os = (Get-CimInstance Win32_OperatingSystem).Caption
$o.usb = @(Get-PnpDevice -PresentOnly -Class HIDClass,USB | Select-Object -ExpandProperty FriendlyName | Sort-Object -Unique)
$o.processes = @(Get-Process | Select-Object -ExpandProperty Name | Sort-Object -Unique)
$o.services = @(Get-Service | Where-Object Status -eq Running | ForEach-Object { $_.Name + '|' + $_.DisplayName })
$o.tasks = @(Get-ScheduledTask | Where-Object State -ne 'Disabled' | ForEach-Object { $_.TaskName })
$o.installed = @(Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*,HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*,HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* | Where-Object DisplayName | ForEach-Object { $_.DisplayName } | Sort-Object -Unique)
$o.pawnio = [bool](Get-Service PawnIO)
$o | ConvertTo-Json -Depth 4 -Compress
"""


def detect_system():
    """Relatório do PC para um agente de IA configurar o EasyRGB sozinho."""
    raw = subprocess.run(["powershell", "-NoProfile", "-Command", _DETECT_PS], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=90).stdout
    def tidy(v):  # o Windows devolve textos com espaços sobrando
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, list):
            return [tidy(x) for x in v]
        if isinstance(v, dict):
            return {k: tidy(x) for k, x in v.items()}
        return v
    s = tidy(json.loads(raw or "{}"))
    found = []
    for name, pat in _RGB_SOFTWARE.items():
        hit = {k: [x for x in (s.get(k) or []) if re.search(pat, str(x), re.I)]
               for k in ("processes", "services", "tasks", "installed")}
        if any(hit.values()):
            found.append({"software": name, "running": bool(hit["processes"] or hit["services"]),
                          "starts_with_windows": bool(hit["tasks"] or hit["services"]), "evidence": hit})
    report = {
        "app": {"name": APP_NAME, "version": VERSION, "folder": str(ROOT), "packaged_exe": FROZEN,
                "openrgb_installed": OPENRGB_EXE.exists(), "openrgb_running": openrgb_running(),
                "pawnio_driver": bool(s.get("pawnio")), "library_ok": (HERE / "lib" / "openrgb").exists(),
                "ui_url": f"http://127.0.0.1:{UI_PORT}/", "pc_profile": PC_FILE.exists()},
        "system": {k: s.get(k) for k in ("motherboard", "bios", "cpu", "ram", "gpu", "os")},
        "usb_hid_devices": s.get("usb"),
        "rgb_software_conflicts": found,
        "vendor_bridges": vendors.detect_bridges(),
        "openrgb_devices": [],
    }
    if openrgb_running():
        try:
            report["openrgb_devices"] = device_info()
        except Exception as e:
            report["openrgb_error"] = str(e)
    tips = []
    if not OPENRGB_EXE.exists() or not s.get("pawnio"):
        tips.append("Falta instalar: peça para o usuário abrir o EasyRGB.bat (pede admin uma vez).")
    if not openrgb_running():
        tips.append("OpenRGB fechado: rode 'python rgb_controller.py conectar' ou abra o EasyRGB.bat.")
    if any(f["running"] for f in found):
        tips.append("Há software RGB de fabricante rodando: ele pode sobrescrever as cores. Pergunte ao usuário "
                    "antes de desativar a inicialização dele (nunca desinstale).")
    for b in report["vendor_bridges"]:
        if b["installed"]:
            tips.append(f"{b['app']} instalado: o EasyRGB pinta por cima dele (sem desativar). Peça para ligar no "
                        "programa a opção que deixa jogos/aplicativos controlarem a iluminação e pergunte quais "
                        "periféricos dessa marca a pessoa tem, para preencher pc.json -> vendors.")
    if openrgb_running() and not report["openrgb_devices"]:
        tips.append("OpenRGB não achou dispositivos: confira https://openrgb.org/devices.html, se o OpenRGB está "
                    "como admin e se o RGB não está desligado na BIOS.")
    report["next_steps"] = tips
    return report


_conf_cache = {"t": 0.0, "v": []}


def running_conflicts():
    """Programas RGB de fabricante abertos agora (podem trocar as cores por cima do EasyRGB). Cache de 15 s."""
    if time.time() - _conf_cache["t"] < 15:
        return _bridged(_conf_cache["v"])
    try:
        procs = running_processes()
        hits = [name for name, pat in _RGB_SOFTWARE.items()
                if "Wallpaper" not in name and any(re.search(pat, p, re.I) for p in procs)]
    except Exception:
        hits = []
    _conf_cache.update(t=time.time(), v=hits)
    return _bridged(hits)


def _bridged(hits):
    """Tira da lista os programas que o EasyRGB já controla por cima (não brigam mais)."""
    apps = {b.app for b in vendors.BRIDGES if b.key in _vend["keys"]}
    return [h for h in hits if h not in apps]


_pc_cache = {"key": None, "v": None}


def load_pc():
    """Perfil do PC. Lido de novo só quando o arquivo muda (o efeito animado consulta isto a cada quadro)."""
    try:
        st = PC_FILE.stat()
        key = (str(PC_FILE), st.st_mtime_ns, st.st_size)
    except OSError:
        _pc_cache.update(key=None, v=None)
        return None
    if key != _pc_cache["key"]:
        try:
            _pc_cache.update(key=key, v=json.loads(PC_FILE.read_text(encoding="utf-8")))
        except Exception:
            return None
    return json.loads(json.dumps(_pc_cache["v"])) if _pc_cache["v"] is not None else None


_TYPE_NAMES = {
    "pt": {"MOTHERBOARD": "Placa-mãe", "DRAM": "Memória RAM", "KEYBOARD": "Teclado", "MOUSE": "Mouse",
           "GPU": "Placa de vídeo", "COOLER": "Cooler", "LEDSTRIP": "Fita de LED", "MOUSEMAT": "Mousepad",
           "HEADSET": "Headset", "SPEAKER": "Caixa de som", "CASE": "Gabinete"},
    "en": {"MOTHERBOARD": "Motherboard", "DRAM": "Memory", "KEYBOARD": "Keyboard", "MOUSE": "Mouse",
           "GPU": "Graphics card", "COOLER": "Cooler", "LEDSTRIP": "LED strip", "MOUSEMAT": "Mousepad",
           "HEADSET": "Headset", "SPEAKER": "Speaker", "CASE": "Case"}}


def auto_profile(devs, lang="pt"):
    """Perfil do PC feito pelo próprio app (assistente da primeira vez), sem agente de IA:
    apelidos com a marca ("Teclado Logitech"), RAMs iguais e um resumo curto."""
    names = _TYPE_NAMES.get(lang, _TYPE_NAMES["en"])
    nick = {}
    for d in devs:
        base = names.get(d.get("type"))
        if not base:
            continue
        v = (d.get("vendor") or "").strip()
        good_vendor = v and v.lower() not in base.lower() and d.get("type") != "DRAM" and len(v) <= 20
        nick[str(d["id"])] = f"{base} {v}" if good_vendor else base
    types = [d.get("type") for d in devs]
    seen, summary = set(), []
    for d in devs:
        n = nick.get(str(d["id"]), d.get("name", ""))
        if n not in seen:
            seen.add(n)
            summary.append(n + (f" ({types.count(d.get('type'))})" if d.get("type") == "DRAM" and types.count("DRAM") > 1 else ""))
    return {"agent": "EasyRGB", "summary": ", ".join(summary), "nicknames": nick,
            "links": {"DRAM": "mirror"} if types.count("DRAM") > 1 else {},
            "notes": ["Configurado pelo assistente do próprio app." if lang == "pt" else "Set up by the app's own wizard."]}


def run_setup(body):
    """Assistente da primeira vez: salva o perfil do PC, aplica o estilo escolhido e (se pedido) liga o
    "Restaurar ao ligar o PC"."""
    lang = body.get("lang") if body.get("lang") in _TYPE_NAMES else "pt"
    devs = device_info()
    prof = save_pc(auto_profile(devs, lang))
    colors = parse_colors(body.get("colors") or [])
    if not colors:
        raise ValueError("Escolha um estilo")
    links = {"ram": "mirror"} if prof["links"].get("DRAM") else {}
    rep, _ = apply_claude({"name": body.get("name") or "Meu estilo", "colors": [to_hex(c) for c in colors],
                           "mode": "gradiente", "brightness": 100, "effect": "static", "links": links})
    auto = None
    if body.get("autostart"):
        auto = set_autostart(True)
    return {"ok": True, "pc": prof, "report": rep, "autostart": auto}


def save_pc(p):
    """Perfil do PC: {"summary", "motherboard", "nicknames": {"<id>": "nome"}, "links": {"DRAM": "span"},
    "notes": [...], "agent": "Claude Code"}"""
    if not isinstance(p, dict):
        raise ValueError("Perfil do PC precisa ser um objeto JSON")
    p = dict(p, configured=time.strftime("%Y-%m-%d %H:%M:%S"))
    PC_FILE.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------- estado salvo
def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def apply_saved(state=None, persist=False, **changes):
    """Reaplica o último estado salvo (ou outro), com mudanças opcionais (ex.: palette, brightness)."""
    L = dict(state or load_state() or {})
    L.update({k: v for k, v in changes.items() if v is not None})
    pal = parse_colors(L.get("palette") or ["#FFFFFF"])
    ui = L.get("ui") or {}
    stop_effect()
    rep = apply(pal, int(L.get("brightness", 100)), L.get("mode", "gradiente"), L.get("devices"), False,
                overrides=L.get("overrides"), groups=L.get("groups"), hw=L.get("hw"), persist=persist, ui=ui)
    if has_animation(ui):
        start_effect(pal, int(L.get("brightness", 100)), L.get("mode", "gradiente"), L.get("devices"),
                     float(ui.get("speed", 3)), L.get("overrides"), L.get("groups"), ui["effect"], L.get("hw"), ui)
    return rep


# ---------------------------------------------------------------- automação: jogos e horários
AUTO_FILE = HERE / "automations.json"
# executável -> preset sugerido (o usuário pode trocar ou adicionar outros pela interface)
KNOWN_GAMES = {
    "VALORANT-Win64-Shipping.exe": "Valorant", "Cyberpunk2077.exe": "Cyberpunk 2077", "portal2.exe": "Portal",
    "GTA5.exe": "GTA VI", "GTA5_Enhanced.exe": "GTA VI",
    "cs2.exe": "Fogo", "FortniteClient-Win64-Shipping.exe": "Vaporwave", "Minecraft.Windows.exe": "Matrix",
    "League of Legends.exe": "Aurora", "RocketLeague.exe": "Oceano", "Overwatch.exe": "Pôr do Sol",
    "eldenring.exe": "Fogo", "hollow_knight.exe": "Branco Frio", "DOOMEternalx64vk.exe": "Fogo",
    "DOOMTheDarkAges.exe": "Fogo", "HaloInfinite.exe": "Matrix", "MCC-Win64-Shipping.exe": "Matrix",
    "destiny2.exe": "Aurora", "GenshinImpact.exe": "Aurora", "Hades.exe": "Fogo", "Hades2.exe": "Fogo",
    "Among Us.exe": "Vaporwave",
}
_auto = {"game": None, "fired": {}, "status": "", "thread": None}


def load_auto():
    try:
        a = json.loads(AUTO_FILE.read_text(encoding="utf-8"))
    except Exception:
        a = {}
    a.setdefault("enabled", True)
    a.setdefault("games", [])
    a.setdefault("schedule", [])
    a.setdefault("hotkeys", False)
    a["hotkey_map"] = clean_hotkeys(a.get("hotkey_map"))
    a.pop("extras", None)   # sobra da versão com "temperatura do PC" (removida)
    return a


def save_auto(a):
    clean = {"enabled": bool(a.get("enabled", True)),
             "hotkeys": bool(a.get("hotkeys", False)),
             "hotkey_map": clean_hotkeys(a.get("hotkey_map")),
             "games": [{"process": str(g["process"]).strip(), "preset": g.get("preset", ""),
                        "enabled": g.get("enabled", True), **({"name": str(g["name"])[:80]} if g.get("name") else {})}
                       for g in a.get("games", []) if g.get("process")],
             "schedule": [{"time": str(s["time"])[:5], "action": s.get("action", "preset"), "value": s.get("value"),
                           "enabled": s.get("enabled", True), **({"tag": s["tag"]} if s.get("tag") else {})}
                          for s in a.get("schedule", []) if re.fullmatch(r"\d{2}:\d{2}", str(s.get("time", ""))[:5])]}
    AUTO_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    return clean


def running_processes():
    """Nomes dos executáveis abertos (em minúsculas)."""
    try:
        return set(vendors.process_table())
    except Exception:
        pass
    out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    return {line.split('","')[0].strip('"').lower() for line in out.splitlines() if line.startswith('"')}


def game_rule(auto, running):
    """Primeira regra de jogo ativa cujo executável está aberto (ou None)."""
    if not auto.get("enabled", True):
        return None
    for g in auto.get("games", []):
        if g.get("enabled", True) and str(g.get("process", "")).lower() in running:
            return g
    return None


def due_schedules(auto, now_hm, today, fired):
    """Horários que devem disparar agora; 'fired' guarda {índice: data} para disparar uma vez por dia."""
    if not auto.get("enabled", True):
        return []
    due = []
    for i, s in enumerate(auto.get("schedule", [])):
        if s.get("enabled", True) and s.get("time") == now_hm and fired.get(i) != today:
            fired[i] = today
            due.append(s)
    return due


def run_schedule(s):
    act, val = s.get("action"), s.get("value")
    if act == "off":
        stop_effect()
        turn_off()
    elif act == "restore":
        apply_saved()
    elif act == "brightness":
        apply_saved(brightness=int(val or 30))
    elif act == "preset":
        _, hexes = find_preset(str(val or ""))
        if hexes:
            apply_saved(persist=True, palette=hexes, overrides={}, hw={})


def vendor_tick():
    """O programa do fabricante (G HUB) abriu ou reabriu depois do EasyRGB, por exemplo ao ligar o PC:
    conecta de novo e repinta o visual salvo por cima dele."""
    if os.environ.get("EASYRGB_NO_VENDORS") or not openrgb_running():
        return
    try:
        vendor_devices(client(autostart=False).devices)
    except Exception:
        return
    for b in vendors.BRIDGES:
        if b.key in _vend["keys"] and (b.restarted() or not b.ok) and time.time() >= b.retry_at and load_state():
            try:
                apply_saved()
            except Exception:
                pass
            return


def auto_tick():
    """Um passo do motor de automação (chamado a cada poucos segundos)."""
    vendor_tick()
    auto = load_auto()
    if not _auto["game"] and not (auto.get("enabled", True) and (auto.get("games") or auto.get("schedule"))):
        return   # sem regras: não gasta nada
    if not openrgb_running():
        return
    rule = game_rule(auto, running_processes()) if auto.get("games") else None
    cur = _auto["game"]
    if rule and (not cur or cur["process"] != rule["process"]):
        _, hexes = find_preset(rule.get("preset", ""))
        if hexes:
            apply_saved(palette=hexes, overrides={}, hw={})   # não salva: ao fechar o jogo volta ao normal
            _auto["game"] = rule
            _auto["status"] = f"{rule['process']} aberto: usando {rule['preset']}"
    elif not rule and cur:
        _auto["game"] = None
        _auto["status"] = ""
        apply_saved()
    now = time.localtime()
    for s in due_schedules(auto, time.strftime("%H:%M", now), time.strftime("%Y-%m-%d", now), _auto["fired"]):
        if not _auto["game"]:  # jogando, o jogo tem prioridade
            run_schedule(s)


def start_auto_engine(interval=4):
    def loop():
        while True:
            try:
                auto_tick()
            except Exception as e:
                _auto["status"] = f"erro na automação: {e}"
            time.sleep(interval)
    if not _auto["thread"]:
        _auto["thread"] = threading.Thread(target=loop, daemon=True)
        _auto["thread"].start()


def find_installed_games(force=False):
    """Jogos instalados (Steam, Epic, GOG, Ubisoft, EA, Xbox, Riot, Battle.net), com o executável principal."""
    import games
    return games.find_games(KNOWN_GAMES, force=force)


# ---------------------------------------------------------------- iniciar com o Windows
TASK_NAME = "EasyRGB"


_autostart_cache = {"t": 0.0, "v": False}


# ---------------------------------------------------------------- atualização automática
_update = {"t": 0.0, "v": None}


def _ver(s):
    return tuple(int(x) for x in re.findall(r"\d+", str(s))[:3]) or (0,)


def check_update(force=False):
    """Vê no GitHub se saiu versão nova (no máximo a cada 6 h). Não manda nenhum dado do PC."""
    if not force and _update["v"] is not None and time.time() - _update["t"] < 6 * 3600:
        return _update["v"]
    import urllib.request
    info = {"current": VERSION, "available": False}
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"User-Agent": "EasyRGB-updater", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            j = json.loads(r.read())
        tag = str(j.get("tag_name", "")).lstrip("vV")
        asset = next((a["browser_download_url"] for a in j.get("assets", []) if a.get("name", "").endswith(".zip")), None)
        info.update(latest=tag, available=_ver(tag) > _ver(VERSION), url=asset, page=j.get("html_url"),
                    can_install=FROZEN and bool(asset))
    except Exception as e:
        info["error"] = str(e)
    _update.update(t=time.time(), v=info)
    return info


def install_update():
    """Baixa o zip da versão nova, espera o EasyRGB fechar, troca os arquivos e abre de novo.
    Os dados do PC (pasta app/) e o OpenRGB não são tocados."""
    info = check_update(force=True)
    if not info.get("available"):
        raise RuntimeError("Você já está na versão mais nova.")
    if not info.get("can_install"):
        raise RuntimeError("Atualização automática só no EasyRGB.exe. Baixe a versão nova no GitHub.")
    import tempfile
    import urllib.request
    import zipfile
    work = Path(tempfile.gettempdir()) / "easyrgb-update"
    shutil_rm(work)
    work.mkdir(parents=True)
    zpath = work / "EasyRGB-windows.zip"
    req = urllib.request.Request(info["url"], headers={"User-Agent": "EasyRGB-updater"})
    with urllib.request.urlopen(req, timeout=120) as r, open(zpath, "wb") as f:
        f.write(r.read())
    with zipfile.ZipFile(zpath) as z:
        z.extractall(work / "new")
    src = work / "new" / "EasyRGB"
    if not (src / "EasyRGB.exe").exists():
        raise RuntimeError("O download da atualização veio incompleto. Tente de novo.")
    dst = Path(sys.executable).parent
    script = work / "atualizar.ps1"
    script.write_text(f"""$ErrorActionPreference = 'SilentlyContinue'
Wait-Process -Id {os.getpid()} -Timeout 60
Start-Sleep 1
Get-ChildItem -LiteralPath '{src}' | Where-Object {{ $_.Name -notin @('app','OpenRGB','download') }} | ForEach-Object {{
  Copy-Item -LiteralPath $_.FullName -Destination '{dst}' -Recurse -Force }}
Start-Process -FilePath '{dst / "EasyRGB.exe"}' -ArgumentList '--no-browser' -WorkingDirectory '{dst}'
""", encoding="utf-8-sig")
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:   # sai do "grupo" do EasyRGB, para o atualizador continuar vivo quando o app fechar
        subprocess.Popen(cmd, creationflags=flags | 0x01000000, close_fds=True)   # CREATE_BREAKAWAY_FROM_JOB
    except OSError:
        subprocess.Popen(cmd, creationflags=flags | getattr(subprocess, "DETACHED_PROCESS", 0), close_fds=True)
    threading.Timer(1.0, lambda: os._exit(0)).start()   # fecha para liberar os arquivos
    return {"ok": True, "version": info["latest"]}


def shutil_rm(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def vendor_sdks():
    """Baixa o kit oficial que uma ponte precisa (hoje: iCUE SDK da Corsair), só quando o programa da marca existe."""
    try:
        import vendors_more
        b = vendors_more.CorsairBridge()
        if b.installed() and not b.dll_path():
            print("Corsair iCUE SDK:", vendors_more.download_corsair_sdk())
    except Exception as e:
        _log_once(f"kit da Corsair: {e!r}")


# ---------------------------------------------------------------- idiomas extras (feitos por IA)
LANG_DIRS = (HERE / "lang", RES / "lang")   # os da pessoa (app/lang) e os que vêm com o app


def ui_strings():
    """Todos os textos da interface: {texto original: inglês}, lidos da tabela EN do index.html."""
    html = (RES / "index.html").read_text(encoding="utf-8")
    a = html.index("const EN={") + len("const EN=")
    b = html.index("\n};", a) + 2
    body = "\n".join(l for l in html[a:b].splitlines() if not l.strip().startswith("//"))
    body = re.sub(r",\s*}$", "}", body.strip())
    return json.loads(body)


def lang_file(code):
    for d in LANG_DIRS:
        f = d / f"{code}.json"
        if f.exists():
            return f
    return None


def lang_template(code):
    """Cria app/lang/<código>.json com os textos em inglês para traduzir (mantém o que já estiver traduzido)."""
    if not re.fullmatch(r"[a-z]{2,3}", code or ""):
        raise ValueError("Use o código do idioma com 2 ou 3 letras, ex.: es, ru, de, fr, ja")
    src = ui_strings()
    f = HERE / "lang" / f"{code}.json"
    old = {}
    if lang_file(code):
        old = json.loads(lang_file(code).read_text(encoding="utf-8")).get("strings", {})
    data = {"code": code, "name": "", "note": "Translate every value (keep the keys, keep {placeholders}, keep it short).",
            "english": src, "strings": {k: old.get(k, "") for k in src}}
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        cur = json.loads(f.read_text(encoding="utf-8"))
        data["name"] = cur.get("name", "")
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return f, sum(1 for v in data["strings"].values() if not v), len(src)


def lang_check(code):
    """Confere uma tradução: o que falta e placeholders {x} que sumiram."""
    f = lang_file(code)
    if not f:
        raise ValueError(f"Não existe app/lang/{code}.json. Rode: idioma {code}")
    data = json.loads(f.read_text(encoding="utf-8"))
    src, got = ui_strings(), data.get("strings", {})
    missing = [k for k in src if not got.get(k)]
    broken = [k for k in src if got.get(k) and set(re.findall(r"\{\w+\}", k)) != set(re.findall(r"\{\w+\}", got[k]))]
    return {"file": str(f), "name": data.get("name"), "total": len(src), "missing": len(missing),
            "broken_placeholders": broken[:20], "examples_missing": missing[:10]}


# ---------------------------------------------------------------- backup, diagnóstico e desfazer
BACKUP_FILES = {"pc": "pc.json", "look": "last_state.json", "automations": "automations.json",
                "my_presets": "my_presets.json", "ai": "claude_color.json"}


def make_backup():
    """Tudo o que a pessoa configurou, num JSON só (para guardar ou levar para outro PC)."""
    out = {"easyrgb_backup": 1, "version": VERSION, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    for key, name in BACKUP_FILES.items():
        f = HERE / name
        if f.exists():
            try:
                out[key] = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                pass
    return out


def restore_backup(data, apply_now=True):
    """Volta um backup. Só aceita arquivo do EasyRGB; guarda o estado atual antes, em app/antes-de-restaurar.json."""
    if not isinstance(data, dict) or data.get("easyrgb_backup") != 1:
        raise ValueError("Este arquivo não é um backup do EasyRGB")
    (HERE / "antes-de-restaurar.json").write_text(json.dumps(make_backup(), ensure_ascii=False, indent=1), encoding="utf-8")
    done = []
    for key, name in BACKUP_FILES.items():
        if key in data and data[key] is not None:
            if key == "automations":
                save_auto(data[key])
            else:
                (HERE / name).write_text(json.dumps(data[key], ensure_ascii=False, indent=2), encoding="utf-8")
            done.append(key)
    _pc_cache.update(key=None, v=None)
    if apply_now and "look" in done:
        try:
            apply_saved()
        except Exception:
            pass
    sync_hotkeys()
    return done


def diagnostics():
    """Relatório para um agente de IA achar problemas (não aparece na interface). Sem senhas nem tokens."""
    import platform
    rep = {"easyrgb": VERSION, "frozen": FROZEN, "python": sys.version.split()[0], "windows": platform.platform(),
           "folder": str(ROOT), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    checks = {
        "openrgb_running": openrgb_running,
        "openrgb_installed": lambda: OPENRGB_EXE.exists(),
        "pawnio_service": lambda: subprocess.run(["sc", "query", "PawnIO"], capture_output=True,
                                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0,
        "configured_ok": lambda: (ROOT / "configurado.ok").exists(),
        "autostart_task": autostart_task_command,
        "autostart_ok": lambda: autostart_installed(fresh=True),
        "devices": lambda: [{k: d.get(k) for k in ("id", "name", "type", "backend", "vendor", "persist")}
                            | {"leds": sum(z["leds"] for z in d.get("zones", []))} for d in device_info()],
        "bridges": lambda: vendors.detect_bridges(),
        "bridge_state": lambda: [{"key": b.key, "active": b.key in _vend["keys"], "ok": getattr(b, "ok", None),
                                  "connects": getattr(b, "connects", 0), "fails": getattr(b, "fails", 0)} for b in vendors.BRIDGES],
        "conflicts": running_conflicts,
        "effect": lambda: {"on": _effect["on"], "kind": _effect.get("kind")},
        "hotkeys": lambda: {"on": load_auto().get("hotkeys"), "errors": list(_hk["errors"]), "map": load_auto().get("hotkey_map")},
        "automations": lambda: {"games": len(load_auto().get("games", [])), "schedules": len(load_auto().get("schedule", []))},
        "update": lambda: check_update(),
        "selftest_libs": lambda: {n: (__import__(n) and "ok") for n in ("openrgb", "PIL", "pystray")},
        "files": lambda: {n: (HERE / n).exists() for n in BACKUP_FILES.values()},
    }
    for name, fn in checks.items():
        try:
            rep[name] = fn()
        except Exception as e:
            rep[name] = f"ERRO: {e!r}"
    try:
        rep["log_tail"] = (HERE / "easyrgb.log").read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
    except OSError:
        rep["log_tail"] = []
    return rep


def undo_everything(delete_data=False):
    """'Desfazer tudo': devolve o PC ao estado de antes do EasyRGB (menos desinstalar os arquivos).
    Religa o ASRock Polychrome, tira o 'Restaurar ao ligar o PC', solta o teclado para o programa da marca,
    tira o EasyRGB do Claude Desktop e (se pedido) apaga os dados da pessoa. Pede administrador uma vez."""
    stop_effect()
    for b in vendors.BRIDGES:
        try:
            b.stop()   # o G HUB e afins voltam ao perfil deles
        except Exception:
            pass
    import tempfile
    script = Path(tempfile.gettempdir()) / "easyrgb_desfazer.ps1"
    script.write_text(f"""$ErrorActionPreference = 'SilentlyContinue'
Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false
if (Get-ScheduledTask -TaskName AsrPolychromeRGB) {{ Enable-ScheduledTask -TaskName AsrPolychromeRGB | Out-Null }}
Get-Process OpenRGB | Stop-Process -Force
""", encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden "
                    f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{script}'"],
                   check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    done = {"autostart_removed": not autostart_installed(fresh=True)}
    try:
        import mcp_server
        done["ai_apps"] = mcp_server.disconnect_all()   # tira o EasyRGB de todas as IAs (Claude, Cursor, Copilot...)
    except Exception:
        done["ai_apps"] = []
    if delete_data:
        (HERE / "antes-de-desfazer.json").write_text(json.dumps(make_backup(), ensure_ascii=False, indent=1),
                                                    encoding="utf-8")   # última cópia, por segurança
        for name in BACKUP_FILES.values():
            try:
                (HERE / name).unlink()
            except OSError:
                pass
        done["data_deleted"] = True
    return done


def first_run_setup():
    """Primeira vez do EasyRGB.exe: roda o instalador (OpenRGB oficial + driver PawnIO) como administrador e espera."""
    setup = ROOT / "1-Configurar (admin).ps1"
    if not setup.exists():
        return False
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Start-Process powershell -Verb RunAs -Wait -ArgumentList "
                    f"'-NoProfile','-ExecutionPolicy','Bypass','-File','\"{setup}\"'"],
                   check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return (ROOT / "configurado.ok").exists()


def launcher():
    """Programa que a tarefa de inicialização chama. O pyw.exe do Windows acha o Python instalado na hora,
    então trocar ou atualizar o Python não quebra o "Restaurar ao ligar o PC"."""
    if FROZEN:
        return Path(sys.executable)
    pyw = Path(os.environ.get("WINDIR", r"C:\Windows")) / "pyw.exe"
    if pyw.exists():
        return pyw
    own = Path(sys.executable).with_name("pythonw.exe")
    return own if own.exists() else Path(sys.executable)


def autostart_task_command():
    """Programa que a tarefa chama hoje (None se não existe)."""
    r = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME, "/xml"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        return None
    raw = r.stdout
    xml = raw.decode("utf-16", errors="ignore") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else \
        raw.decode("utf-8", errors="ignore")
    m = re.search(r"<Command>(.*?)</Command>", xml)
    return m.group(1).strip().strip('"') if m else ""


def autostart_installed(fresh=False):
    """A tarefa existe E o programa que ela chama ainda existe (ex.: o Python antigo não foi desinstalado)."""
    if not fresh and time.time() - _autostart_cache["t"] < 30:
        return _autostart_cache["v"]
    cmd = autostart_task_command()
    _autostart_cache.update(t=time.time(), v=bool(cmd) and Path(cmd).exists())
    return _autostart_cache["v"]


def set_autostart(on):
    """Cria/remove uma tarefa no logon (como admin, para o OpenRGB acessar o chip sem pedir UAC a cada boot).
    Pede administrador uma vez."""
    exe = launcher()
    import tempfile
    user = os.environ.get("USERDOMAIN", "") + "\\" + os.environ.get("USERNAME", "")
    if on:
        arg = "--background" if FROZEN else f'"{SRC / "rgb_controller.py"}" --background'   # o .exe chama ele mesmo
        ps = (f"$a = New-ScheduledTaskAction -Execute '{exe}' -Argument '{arg}' "
              f"-WorkingDirectory '{HERE}'\n"
              f"$t = New-ScheduledTaskTrigger -AtLogOn -User '{user}'\n"
              f"$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
              f"-ExecutionTimeLimit ([TimeSpan]::Zero)\n"
              f"$p = New-ScheduledTaskPrincipal -UserId '{user}' -LogonType Interactive -RunLevel Highest\n"
              f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Settings $s -Principal $p -Force\n")
    else:
        ps = f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false\n"
    script = Path(tempfile.gettempdir()) / "easyrgb_autostart.ps1"
    script.write_text(ps, encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden "
                    f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{script}'"],
                   check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        script.unlink()
    except OSError:
        pass
    return autostart_installed(fresh=True)


def needs_running():
    """Só precisa ficar aberto se tiver algo que muda as cores com o tempo."""
    a = load_auto()
    if a.get("enabled", True) and (any(g.get("enabled", True) for g in a.get("games", []))
                                   or any(s.get("enabled", True) for s in a.get("schedule", []))):
        return True
    if a.get("hotkeys"):   # atalhos de teclado precisam do EasyRGB aberto (escondido, na bandeja)
        return True
    if vendor_devices() or _vend["keys"]:   # G HUB e cia. voltam ao perfil deles se o EasyRGB fechar
        return True
    return has_animation((load_state() or {}).get("ui"))


def restore_on_boot():
    """Modo --background (ao ligar o PC): abre o OpenRGB, devolve o último visual e, se nada precisar ficar
    rodando (modo jogo, horários ou efeito animado), fecha o OpenRGB e o EasyRGB: não fica nada na memória.
    As cores continuam nos chips até o PC desligar."""
    was_open = openrgb_running()
    for _ in range(3):
        if start_openrgb():
            break
        time.sleep(5)
    for _ in range(30):
        try:
            client(refresh=True)
            if load_state():
                apply_saved()
            break
        except Exception:
            time.sleep(2)
    if not needs_running():
        time.sleep(1)
        if not was_open:
            subprocess.run(["taskkill", "/im", "OpenRGB.exe", "/f"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        os._exit(0)


# ---------------------------------------------------------------- compartilhar visual
def share_code(L):
    """Código curto para compartilhar um visual (independente do hardware de quem recebe)."""
    import base64
    ui = L.get("ui") or {}
    data = {"v": 1, "c": [to_hex(c) for c in parse_colors(L.get("palette") or L.get("colors") or [])],
            "m": L.get("mode", "gradiente"), "b": int(L.get("brightness", 100)),
            "e": ui.get("effect", "static"), "s": ui.get("speed", 3), "l": ui.get("links") or {}}
    if L.get("name"):
        data["n"] = L["name"]
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
    return "EASYRGB1-" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def read_share_code(code):
    import base64
    code = str(code).strip()
    prefix = next((p for p in ("EASYRGB1-", "MEURGB1-") if code.upper().startswith(p)), None)  # MEURGB1-: nome antigo
    if not prefix:
        raise ValueError("Código inválido: precisa começar com EASYRGB1-")
    b = code[len(prefix):]
    data = json.loads(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8"))
    cols = [to_hex(c) for c in parse_colors(data.get("c", []))]
    if not cols:
        raise ValueError("Código sem cores")
    return {"name": data.get("n", ""), "colors": cols, "mode": data.get("m", "gradiente"),
            "brightness": int(data.get("b", 100)), "effect": data.get("e", "static"),
            "speed": data.get("s", 3), "links": data.get("l", {})}


# ---------------------------------------------------------------- ações rápidas (atalhos e bandeja)
_rev = {"n": 0, "off": False, "msg": ""}   # a interface recarrega quando "n" muda
_FX_CYCLE = ("static", "onda", "respirar", "estrelas", "musica")


def _pt():
    """Idioma do Windows é português? (para os textos da bandeja e avisos)"""
    try:
        import ctypes
        return (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x16
    except Exception:
        return True


def _bump(msg=""):
    _rev["n"] += 1
    _rev["msg"] = msg
    tray = _tray.get("icon")
    if tray:
        try:
            tray.update_menu()
            if msg:
                tray.notify(msg, APP_NAME)
        except Exception:
            pass


def quick(action, value=None):
    """Ações rápidas usadas pelos atalhos de teclado e pela bandeja. Salvam o visual."""
    L = load_state() or {"palette": ["#FF2E88", "#00D9C8"], "brightness": 100, "ui": {}}
    ui = dict(L.get("ui") or {})
    pt = _pt()
    if action in ("next", "prev", "preset"):
        names = list(load_palettes())
        if not names:
            return
        if action == "preset":
            name = value
        else:
            cur = ui.get("preset")
            i = names.index(cur) if cur in names else -1
            name = names[(i + (1 if action == "next" else -1)) % len(names)]
        ui["preset"] = name
        _rev["off"] = False
        apply_saved(L, persist=True, palette=load_palettes()[name], overrides={}, hw={}, ui=ui)
        _bump(("Preset: " if pt else "Preset: ") + name)
    elif action == "toggle":
        if _rev["off"]:
            _rev["off"] = False
            apply_saved(L)
            _bump("Luzes acesas" if pt else "Lights on")
        else:
            _rev["off"] = True
            stop_effect()
            turn_off()
            _bump("Luzes apagadas" if pt else "Lights off")
    elif action in ("brighter", "dimmer", "brightness"):
        b = int(value) if action == "brightness" else int(L.get("brightness", 100)) + (10 if action == "brighter" else -10)
        b = max(5, min(100, b))
        _rev["off"] = False
        apply_saved(L, persist=True, brightness=b)
        _bump(("Brilho " if pt else "Brightness ") + f"{b}%")
    elif action in ("effect", "next_effect"):
        cur = ui.get("effect", "static")
        ui["effect"] = value if action == "effect" else _FX_CYCLE[(_FX_CYCLE.index(cur) + 1) % len(_FX_CYCLE)
                                                                  if cur in _FX_CYCLE else 0]
        _rev["off"] = False
        apply_saved(L, persist=True, ui=ui)
        names = {"static": ("Estático", "Static"), "fluir": ("Fluir", "Flow"), "respirar": ("Respirar", "Breathe"),
                 "musica": ("Música", "Music"), "ciclo": ("Ciclo de cores", "Color cycle"),
                 "arcoiris": ("Arco-íris", "Rainbow"), "onda": ("Onda de cores", "Color wave"),
                 "estrelas": ("Estrelas", "Starlight"), "tela": ("Cor da tela", "Screen color"),
                 "teclas": ("Reação às teclas", "Key ripple")}
        _bump(("Efeito: " if pt else "Effect: ") + names.get(ui["effect"], (ui["effect"],) * 2)[0 if pt else 1])


# Ctrl+Alt + tecla
# atalhos: ação -> combinação ("Ctrl+Alt+Right"). A pessoa escolhe no app; vazio = desligado.
HOTKEY_ACTIONS = ("next", "prev", "brighter", "dimmer", "next_effect", "toggle")
HOTKEY_DEFAULTS = {"next": "Ctrl+Alt+Right", "prev": "Ctrl+Alt+Left", "brighter": "Ctrl+Alt+Up",
                   "dimmer": "Ctrl+Alt+Down", "next_effect": "Ctrl+Alt+E", "toggle": "Ctrl+Alt+L"}
_MODS = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
_VK = {"right": 0x27, "left": 0x25, "up": 0x26, "down": 0x28, "space": 0x20, "home": 0x24, "end": 0x23,
       "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D, "delete": 0x2E, "pause": 0x13,
       **{chr(c).lower(): c for c in range(0x41, 0x5B)}, **{str(d): 0x30 + d for d in range(10)},
       **{f"f{n}": 0x6F + n for n in range(1, 25)}, **{f"num{d}": 0x60 + d for d in range(10)}}
_hk = {"thread": None, "tid": None, "errors": [], "map": None}


def parse_hotkey(combo):
    """"Ctrl+Alt+Right" -> (modificadores, tecla). Exige pelo menos um modificador (menos F13-F24),
    para não roubar uma tecla comum do teclado."""
    parts = [x.strip().lower() for x in str(combo or "").split("+") if x.strip()]
    if not parts:
        return None
    mods = 0
    for m in parts[:-1]:
        if m not in _MODS:
            return None
        mods |= _MODS[m]
    vk = _VK.get(parts[-1])
    if vk is None or (not mods and not 0x7C <= vk <= 0x87):
        return None
    return mods, vk


def clean_hotkeys(m):
    m = m if isinstance(m, dict) else {}
    out = {}
    for act in HOTKEY_ACTIONS:
        v = m.get(act, HOTKEY_DEFAULTS[act])
        out[act] = v if v == "" or parse_hotkey(v) else HOTKEY_DEFAULTS[act]
    return out


def start_hotkeys(hmap=None):
    """Atalhos globais do Windows (funcionam com qualquer janela em foco). Custo: uma thread parada esperando."""
    if _hk["thread"] and _hk["thread"].is_alive():
        return
    hmap = clean_hotkeys(hmap if hmap is not None else load_auto().get("hotkey_map"))
    table = {i + 1: (act, parse_hotkey(c)) for i, (act, c) in enumerate(hmap.items()) if c}
    _hk.update(map=hmap, errors=[])

    def loop():
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        _hk["tid"] = kernel32.GetCurrentThreadId()
        for hid, (act, (mods, vk)) in table.items():
            if not user32.RegisterHotKey(None, hid, mods | 0x4000, vk):   # 0x4000: não repetir segurando
                _hk["errors"].append(act)   # combinação já usada por outro programa
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312 and msg.wParam in table:   # WM_HOTKEY
                try:
                    quick(table[msg.wParam][0])
                except Exception:
                    pass
        for hid in table:
            user32.UnregisterHotKey(None, hid)

    _hk["thread"] = threading.Thread(target=loop, daemon=True)
    _hk["thread"].start()


def stop_hotkeys():
    if _hk["thread"] and _hk["tid"]:
        import ctypes
        ctypes.windll.user32.PostThreadMessageW(_hk["tid"], 0x0012, 0, 0)   # WM_QUIT
        _hk["thread"].join(timeout=2)
    _hk.update(thread=None, tid=None)


def sync_hotkeys():
    a = load_auto()
    if not a.get("hotkeys"):
        return stop_hotkeys()
    if _hk["thread"] and _hk["map"] != a["hotkey_map"]:   # mudou um atalho: registra de novo
        stop_hotkeys()
    start_hotkeys(a["hotkey_map"])


# ícone ao lado do relógio
_tray = {"icon": None}


def _tray_summary():
    """Texto curto do estado atual, para o topo do menu e a dica ao passar o mouse."""
    pt = _pt()
    if _rev["off"]:
        return "Luzes apagadas" if pt else "Lights off"
    L = load_state() or {}
    ui = L.get("ui") or {}
    name = ui.get("preset") or ("Cores personalizadas" if pt else "Custom colors")
    return f"{name} · {int(L.get('brightness', 100))}%"


def start_tray(url):
    """Ícone na bandeja, organizado em seções: estado, abrir, visual (presets, efeito, brilho, luzes),
    atalhos e sair. Os itens marcados mostram o que está ativo agora."""
    try:
        import pystray
        from PIL import Image
    except Exception:
        return
    pt = _pt()
    T = (lambda p, e: p) if pt else (lambda p, e: e)
    Item, Menu = pystray.MenuItem, pystray.Menu

    def act(a, v=None):
        return lambda icon, item: threading.Thread(target=quick, args=(a, v), daemon=True).start()

    def ui():
        return ((load_state() or {}).get("ui") or {})

    def presets_items():
        mine, builtin = list(user_presets()), [n for n in builtin_presets() if n not in user_presets()]
        items = []
        for title, names in ((T("Meus presets", "My presets"), mine), (T("Padrão", "Built-in"), builtin)):
            if not names:
                continue
            if items:
                items.append(Menu.SEPARATOR)
            items.append(Item(title, None, enabled=False))
            items += [Item(n, act("preset", n), radio=True, checked=lambda it, n=n: ui().get("preset") == n)
                      for n in names]
        return items

    fx = [("static", T("Estático", "Static")), ("fluir", T("Fluir", "Flow")), ("respirar", T("Respirar", "Breathe")),
          ("musica", T("Música", "Music")), ("ciclo", T("Ciclo de cores", "Color cycle")),
          ("arcoiris", T("Arco-íris", "Rainbow"))]

    def bri():
        return int((load_state() or {}).get("brightness", 100))

    def toggle_hotkeys(icon, item):
        a = load_auto()
        a["hotkeys"] = not a.get("hotkeys")
        save_auto(a)
        sync_hotkeys()
        _bump((T("Atalhos ligados", "Shortcuts on") if a["hotkeys"] else T("Atalhos desligados", "Shortcuts off")))

    def quit_app(icon, item):
        icon.stop()
        stop_effect()
        os._exit(0)

    menu = Menu(
        Item(lambda it: f"{APP_NAME}  ·  {_tray_summary()}", None, enabled=False),
        Item(T("Abrir o EasyRGB", "Open EasyRGB"), lambda i, it: open_ui(url), default=True),
        Menu.SEPARATOR,
        Item(T("Presets", "Presets"), Menu(lambda: presets_items())),
        Item(T("Efeito", "Effect"), Menu(*[Item(n, act("effect", k), radio=True,
                                                checked=lambda it, k=k: ui().get("effect", "static") == k)
                                           for k, n in fx])),
        Item(T("Brilho", "Brightness"), Menu(*[Item(f"{v}%", act("brightness", v), radio=True,
                                                    checked=lambda it, v=v: bri() == v)
                                               for v in (100, 75, 50, 25)])),
        Item(T("Luzes acesas", "Lights on"), act("toggle"), checked=lambda it: not _rev["off"]),
        Menu.SEPARATOR,
        Item(T("Atalhos de teclado", "Keyboard shortcuts"), toggle_hotkeys, checked=lambda it: bool(load_auto().get("hotkeys"))),
        Menu.SEPARATOR,
        Item(T("Sair do EasyRGB", "Quit EasyRGB"), quit_app),
    )
    img = RES / "tray.png" if (RES / "tray.png").exists() else RES / "icon.ico"   # PNG transparente
    icon = pystray.Icon(APP_NAME, Image.open(img), APP_NAME, menu)   # ao passar o mouse: só o nome
    _tray["icon"] = icon
    threading.Thread(target=icon.run, daemon=True).start()


# ---------------------------------------------------------------- servidor web local
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.path = self.path.split("?", 1)[0]   # ignora ?parâmetros (ex.: /?v=2)
        if self.path in ("/", "/index.html"):
            return self._send(200, (RES / "index.html").read_bytes(), "text/html")
        if self.path in ("/icon.png", "/favicon.ico"):
            return self._send(200, (RES / "icon.png").read_bytes(), "image/png")
        if self.path == "/api/state":
            st = {"app": APP_NAME, "version": VERSION, "palettes": load_palettes(), "user_presets": list(user_presets()),
                  "conflicts": running_conflicts(),
                  "effect": _effect["on"],
                  "effect_kind": _effect.get("kind") if _effect["on"] else "static",
                  "connected": openrgb_running(), "devices": [], "last": None, "claude": load_claude(),
                  "folder": str(ROOT),
                  "pc": load_pc()}
            try:
                st["last"] = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
            if st["connected"]:
                try:
                    st["devices"] = device_info()
                except Exception as e:
                    reset_client()
                    st["error"] = str(e)
                st["conflicts"] = running_conflicts()   # depois dos dispositivos: G HUB com ponte não é conflito
                st["bridges"] = [{"key": b.key, "active": b.key in _vend["keys"], "ok": b.ok,
                                  "connects": getattr(b, "connects", 0), "fails": getattr(b, "fails", 0)}
                                 for b in vendors.BRIDGES]
            return self._send(200, st)
        if self.path == "/api/claude":
            return self._send(200, dict(load_claude(), effect=_effect["on"],
                                        effect_kind=_effect.get("kind") if _effect["on"] else "static",
                                        pc_configured=(load_pc() or {}).get("configured"),
                                        state_rev=_rev["n"]))
        if self.path == "/api/update":
            return self._send(200, check_update())
        if self.path == "/api/ai-apps":   # IAs conhecidas: achadas no PC? conectadas? + config para "Outra IA"
            import mcp_server
            return self._send(200, {"apps": mcp_server.list_clients(), "manual": mcp_server.manual_config()})
        if self.path == "/api/backup":
            return self._send(200, make_backup())
        m = re.fullmatch(r"/lang/([a-z]{2,3})\.json", self.path)
        if m:   # tradução extra (app/lang/<código>.json)
            f = lang_file(m.group(1))
            if not f:
                return self._send(404, {"error": "sem tradução"})
            d = json.loads(f.read_text(encoding="utf-8"))
            return self._send(200, {"name": d.get("name", ""), "strings": {k: v for k, v in d.get("strings", {}).items() if v}})
        if self.path == "/api/detect":
            return self._send(200, detect_system())
        if self.path == "/api/auto":
            return self._send(200, {"auto": load_auto(), "status": _auto["status"],
                                    "game": _auto["game"], "autostart": autostart_installed(),
                                    "known": KNOWN_GAMES, "needs_running": needs_running(),
                                    "hotkey_errors": list(_hk["errors"])})
        if self.path == "/api/games":
            return self._send(200, {"games": find_installed_games(force=True)})
        if self.path == "/api/share":
            L = load_state()
            if not L:
                return self._send(400, {"ok": False, "error": "Aplique um visual antes de compartilhar"})
            return self._send(200, {"code": share_code(L)})
        self._send(404, {"error": "não encontrado"})

    def do_POST(self):
        self.path = self.path.split("?", 1)[0]
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
            if self.path == "/api/connect":
                return self._send(200, {"ok": start_openrgb()})
            if self.path in ("/api/apply", "/api/preview"):
                stop_effect()
                rep = apply(parse_colors(body.get("colors", [])), int(body.get("brightness", 100)),
                            body.get("mode", "gradiente"), body.get("devices"), bool(body.get("save")),
                            overrides=body.get("overrides"), groups=body.get("groups"),
                            persist=self.path == "/api/apply", ui=body.get("ui"), hw=body.get("hw"))
                return self._send(200, {"ok": True, "report": rep})
            if self.path == "/api/effect":
                if body.get("on"):
                    stop_effect()
                    if body.get("persist"):  # "Aplicar" com efeito animado: salva o estado também
                        apply(parse_colors(body.get("colors", [])), int(body.get("brightness", 100)),
                              body.get("mode", "gradiente"), body.get("devices"), False,
                              overrides=body.get("overrides"), groups=body.get("groups"),
                              ui=body.get("ui"), hw=body.get("hw"))
                    start_effect(parse_colors(body.get("colors", [])), int(body.get("brightness", 100)),
                                 body.get("mode", "gradiente"), body.get("devices"), float(body.get("speed", 3)),
                                 body.get("overrides"), body.get("groups"), body.get("kind", "fluir"), body.get("hw"),
                                 body.get("ui"))
                else:
                    stop_effect()
                return self._send(200, {"ok": True, "effect": _effect["on"]})
            if self.path == "/api/off":
                stop_effect()
                turn_off()
                return self._send(200, {"ok": True})
            if self.path == "/api/auto":
                a = save_auto(body)
                sync_hotkeys()
                time.sleep(0.15)   # dá tempo de o Windows dizer se algum atalho já está em uso
                return self._send(200, {"ok": True, "auto": a, "hotkey_errors": list(_hk["errors"])})
            if self.path == "/api/quick":
                quick(body.get("action"), body.get("value"))
                return self._send(200, {"ok": True})
            if self.path == "/api/autostart":
                return self._send(200, {"ok": True, "autostart": set_autostart(bool(body.get("on")))})
            if self.path == "/api/share":
                if body.get("code"):
                    return self._send(200, {"ok": True, "look": read_share_code(body["code"])})
                return self._send(200, {"ok": True, "code": share_code(body)})
            if self.path == "/api/update":   # baixar e instalar a versão nova (só no EasyRGB.exe)
                return self._send(200, install_update())
            if self.path == "/api/restore":
                return self._send(200, {"ok": True, "restored": restore_backup(body)})
            if self.path == "/api/undo":   # "Desfazer tudo" (a interface pede duas confirmações antes)
                if body.get("confirm") != "DESFAZER":
                    raise ValueError("Confirmação ausente")
                res = undo_everything(bool(body.get("delete_data")))
                self._send(200, {"ok": True, "done": res})
                threading.Timer(1.5, lambda: os._exit(0)).start()   # fecha o EasyRGB no fim
                return
            if self.path == "/api/setup":   # assistente da primeira vez (sem precisar de IA)
                return self._send(200, run_setup(body))
            if self.path == "/api/claude":
                rep, prof = apply_claude(body)
                return self._send(200, {"ok": True, "report": rep, "profile": prof, "effect": _effect["on"],
                                        "effect_kind": _effect.get("kind") if _effect["on"] else "static"})
            if self.path == "/api/mcp":   # "Conectar a uma IA": {"app": "cursor"} (sem app: Claude Desktop)
                import mcp_server
                files = mcp_server.connect_client(body.get("app") or "claude-desktop")
                return self._send(200, {"ok": True, "files": [str(f) for f in files], "apps": mcp_server.list_clients()})
            if self.path == "/api/preset":
                name = (body.get("name") or "").strip()
                if body.get("delete"):
                    delete_user_preset(name)
                else:
                    save_user_preset(name, body.get("colors", []))
                return self._send(200, {"ok": True, "palettes": load_palettes(), "user": list(user_presets())})
        except Exception as e:
            return self._send(500, {"ok": False, "error": str(e)})
        self._send(404, {"error": "não encontrado"})


class Server(ThreadingHTTPServer):
    """No Windows, SO_REUSEADDR deixa dois servidores na mesma porta; aqui a porta é exclusiva."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _edge():
    """Navegador baseado em Chromium para o modo "app" (janela própria, sem barra de endereço).
    Edge vem em todo Windows 10/11; Chrome e Brave ficam de reserva. Nenhum: navegador padrão."""
    rel = [("Microsoft", "Edge", "Application", "msedge.exe"), ("Google", "Chrome", "Application", "chrome.exe"),
           ("BraveSoftware", "Brave-Browser", "Application", "brave.exe")]
    bases = [os.environ.get(k, "") for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for r in rel:
        for base in bases:
            if base and Path(base, *r).exists():
                return Path(base, *r)
    return None


def _window_size():
    """Tamanho da janela que cabe em qualquer tela (de notebook 1366x768 a monitor 4K)."""
    try:
        import ctypes
        u = ctypes.windll.user32
        sw, sh = u.GetSystemMetrics(16), u.GetSystemMetrics(17)   # área útil (sem a barra de tarefas)
        return max(400, min(1280, sw - 60)), max(500, min(880, sh - 40))
    except Exception:
        return 1280, 860


def _focus_window(title):
    """Traz para a frente uma janela do EasyRGB que já esteja aberta (em vez de abrir outra)."""
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = u.FindWindowW("Chrome_WidgetWin_1", title)
        if hwnd:
            u.ShowWindow(hwnd, 9)   # SW_RESTORE
            u.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


def open_ui(url=None):
    """Abre a interface numa janela própria (Edge em modo app, perfil separado, ~0 MB a mais no pacote).
    Sem Edge, abre no navegador padrão."""
    url = url or f"http://127.0.0.1:{UI_PORT}/"
    if _focus_window(APP_NAME):
        return
    edge = _edge()
    if edge:
        profile = Path(os.environ.get("LOCALAPPDATA", str(HERE))) / "EasyRGB" / "janela"
        try:
            subprocess.Popen([str(edge), f"--app={url}", f"--user-data-dir={profile}", "--window-size=%d,%d" % _window_size(),
                              "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
                              "--disable-sync", "--disable-extensions"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
            return
        except OSError:
            pass
    webbrowser.open(url)


def serve():
    url = f"http://127.0.0.1:{UI_PORT}/"
    background = "--background" in sys.argv   # iniciado com o Windows: sem janela e sem navegador
    try:
        srv = Server(("127.0.0.1", UI_PORT), Handler)
    except OSError:  # já tem um EasyRGB aberto: só abre a página dele
        if not background:
            print(f"O {APP_NAME} já está aberto, abrindo no navegador...")
            open_ui(url)
        return
    print(f"{APP_NAME} v{VERSION} rodando em {url}  (Ctrl+C para sair)")
    if background:
        threading.Thread(target=restore_on_boot, daemon=True).start()
    elif "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: open_ui(url)).start()
    start_auto_engine()
    threading.Thread(target=check_update, daemon=True).start()   # vê se tem versão nova, sem atrasar nada
    threading.Thread(target=vendor_sdks, daemon=True).start()     # kit da Corsair, só se o iCUE existir
    start_tray(url)
    sync_hotkeys()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------- CLI
def _read_json_arg(argv):
    """JSON de um arquivo ou do stdin ("-"), sempre em UTF-8 (no Windows o padrão do stdin é cp1252)."""
    src = argv[1] if len(argv) > 1 else "-"
    raw = sys.stdin.buffer.read() if src == "-" else Path(src).read_bytes()
    return json.loads(raw.decode("utf-8-sig"))


def _print_report(rep):
    for r in rep:
        print(("  OK   " if r["ok"] else "  ERRO ") + r["device"]
              + (f" ({r['leds']} LEDs)" if r["ok"] else f": {r['error']}"))
    if not rep:
        print("  Nenhum dispositivo RGB foi detectado pelo OpenRGB.")


def cli(argv):
    def opt(name, default=None):
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default

    cmd = argv[0]
    if cmd in ("mcp-claude-desktop", "conectar-ia"):   # conectar-ia [app]: liga o EasyRGB a um app de IA (MCP)
        import mcp_server
        if cmd == "conectar-ia" and len(argv) < 2:
            for c in mcp_server.list_clients():
                print(f"{c['key']:16} {c['name']:26} found={c['found']} connected={c['connected']}")
            print("\nOther AI apps (stdio MCP server):\n" + mcp_server.manual_config()["json"])
            return
        key = argv[1] if cmd == "conectar-ia" else "claude-desktop"
        print("OK:", ", ".join(map(str, mcp_server.connect_client(key))))
        print(next(c["hint"] for c in mcp_server.list_clients() if c["key"] == key))
        return
    if cmd == "autoteste":   # confere se tudo que o app precisa carrega (usado no build do .exe)
        res = {"frozen": FROZEN, "python": sys.version.split()[0]}
        for name, fn in (("openrgb", lambda: __import__("openrgb.utils")), ("pillow", lambda: __import__("PIL.ImageGrab")),
                         ("pystray", lambda: __import__("pystray")), ("pycaw", lambda: __import__("pycaw.pycaw")),
                         ("audio", lambda: AudioMeter().peak() if "--sem-hardware" not in argv else 0),
                         ("screen", lambda: screen_shot().size if "--sem-hardware" not in argv else 0),
                         ("mcp", lambda: __import__("mcp_server")), ("vendors", lambda: vendors.detect_bridges())):
            try:
                fn()
                res[name] = "ok"
            except Exception as e:
                res[name] = f"ERRO: {e!r}"
        for f in ("index.html", "palettes.json", "icon.png", "tray.png"):
            res[f] = "ok" if (RES / f).exists() else "FALTA"
        print(json.dumps(res, indent=2, ensure_ascii=False))
        sys.exit(0 if all(v == "ok" for k, v in res.items() if k not in ("frozen", "python")) else 1)
    if cmd == "idioma":   # cria/confere uma tradução feita por IA: idioma <código> [--verificar]
        code = (argv[1] if len(argv) > 1 else "").lower()
        if "--verificar" in argv:
            print(json.dumps(lang_check(code), indent=2, ensure_ascii=False))
        else:
            f, todo, total = lang_template(code)
            print(f"OK: {f}\n{todo} of {total} texts to translate. Fill \"name\" (e.g. \"Español\") and every value in "
                  f"\"strings\" (keys = original text, \"english\" = meaning). Then: idioma {code} --verificar")
        return
    if cmd == "diagnostico":   # para agentes de IA: relatório completo de problemas (não fica na interface)
        rep = diagnostics()
        out = HERE / "diagnostico.json"
        out.write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(json.dumps({k: v for k, v in rep.items() if k != "log_tail"}, indent=2, ensure_ascii=False, default=str))
        print(f"\nFull report (with the last log lines): {out}")
        return
    if cmd == "backup":   # backup [arquivo.json]
        f = Path(argv[1]) if len(argv) > 1 else HERE / f"backup-{time.strftime('%Y%m%d-%H%M')}.json"
        f.write_text(json.dumps(make_backup(), ensure_ascii=False, indent=1), encoding="utf-8")
        print("OK:", f)
        return
    if cmd == "restaurar":   # restaurar arquivo.json
        print("OK:", restore_backup(json.loads(Path(argv[1]).read_text(encoding="utf-8")), apply_now=False))
        return
    if cmd == "bibliotecas":   # usado pelo instalador: instala as bibliotecas para este Python
        ok = ensure_libs()
        print(("OK: bibliotecas em " if ok else "ERRO ao instalar as bibliotecas em ") + str(LIB))
        sys.exit(0 if ok else 1)
    if cmd == "listar":
        client()
        for d in device_info():
            print(f"[{d['id']}] {d['name']} ({d['type']})")
            print(f"     efeitos do chip: {', '.join(e['name'] for e in d['effects']) or 'nenhum'}")
            for z in d["zones"]:
                print(f"     - zona {z['name']}: {z['leds']} LEDs")
    elif cmd == "detectar":
        print(json.dumps(detect_system(), indent=2, ensure_ascii=False))
    elif cmd == "conectar":
        print("OpenRGB conectado." if start_openrgb() else "Não consegui abrir o OpenRGB.")
    elif cmd == "configurar":
        p = save_pc(_read_json_arg(argv))
        print(f"Perfil do PC salvo em {PC_FILE} ({len(p.get('nicknames') or {})} apelidos). O app atualiza sozinho.")
    elif cmd == "automacao":
        if len(argv) > 1:
            a = save_auto(_read_json_arg(argv))
            print(f"Automação salva: {len(a['games'])} jogos, {len(a['schedule'])} horários. O app aplica sozinho.")
        else:
            print(json.dumps(load_auto(), indent=2, ensure_ascii=False))
    elif cmd == "jogos":
        print(json.dumps(find_installed_games(), indent=2, ensure_ascii=False))
    elif cmd == "iniciar-com-windows":
        on = (argv[1] if len(argv) > 1 else "sim").lower() not in ("nao", "não", "off", "0", "false")
        print("Inicia com o Windows: " + ("sim" if set_autostart(on) else "não"))
    elif cmd == "compartilhar":
        L = load_state()
        print(share_code(L) if L else "Aplique um visual antes de compartilhar.")
    elif cmd == "importar":
        look = read_share_code(argv[1] if len(argv) > 1 else "")
        rep = apply_saved(persist=True, palette=look["colors"], mode=look["mode"], brightness=look["brightness"],
                          overrides={}, hw={}, ui={"effect": look["effect"], "speed": look["speed"],
                                                    "links": look["links"]})
        print(f"Importado: {look.get('name') or 'visual'} -> {' '.join(look['colors'])}")
        _print_report(rep)
    elif cmd == "desligar":
        turn_off()
        print("Tudo apagado.")
    elif cmd == "aplicar":
        arg = argv[1] if len(argv) > 1 else ""
        pal = parse_colors(arg)
        label = "paleta personalizada"
        if not pal:
            label, hexes = find_preset(arg)
            if not hexes:
                sys.exit(f"Não achei preset nem cores em: {arg!r}. Presets: {', '.join(load_palettes())}")
            pal = parse_colors(hexes)
        rep = apply(pal, int(opt("--brilho", 100)), opt("--modo", "gradiente"), save="--gravar" in argv)
        print(f"Aplicado: {label} -> {' '.join(to_hex(c) for c in pal)}")
        _print_report(rep)
    elif cmd in ("ia", "ai", "claude"):
        prof = _read_json_arg(argv)
        import urllib.error
        import urllib.request
        try:  # com o app aberto, vai por ele: a tela atualiza sozinha e o efeito "fluir" funciona
            req = urllib.request.Request(f"http://127.0.0.1:{UI_PORT}/api/claude", data=json.dumps(prof).encode(),
                                         headers={"Content-Type": "application/json"})
            res = json.loads(urllib.request.urlopen(req, timeout=60).read())
            rep, via = res["report"], "app aberto"
        except urllib.error.HTTPError as e:
            sys.exit("ERRO: " + json.loads(e.read() or b"{}").get("error", str(e)))
        except OSError:
            rep, _ = apply_claude(prof, allow_effect=False)
            via = "direto no OpenRGB"
        print(f"Perfil de IA aplicado ({via}): {prof.get('name')} -> {' '.join(prof.get('colors', []))}")
        _print_report(rep)
    else:
        print(__doc__)


if __name__ == "__main__":
    if "--mcp" in sys.argv:   # servidor MCP para apps de IA (Claude Desktop, Cursor...): fala pelo stdin/stdout
        import mcp_server
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        mcp_server.serve()
        sys.exit(0)
    if sys.stderr is None or sys.stdout is None:   # aberto com pythonw (sem janela): erros vão para o log
        _log = open(HERE / "easyrgb.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = _log
        print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {APP_NAME} v{VERSION}")
    ensure_libs()   # Python novo no PC: instala as bibliotecas para ele (só na primeira vez)
    if FROZEN and not sys.argv[1:] and not (ROOT / "configurado.ok").exists():
        first_run_setup()   # EasyRGB.exe aberto pela primeira vez: instala OpenRGB e driver (pede admin uma vez)
    args = [a for a in sys.argv[1:] if a not in ("--no-browser", "--background")]
    if args:
        cli(args)
    else:
        serve()
