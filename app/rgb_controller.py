"""MeuRGB v1 - controlador RGB por paletas, em cima do OpenRGB (servidor SDK na porta 6742).

Uso:
  python rgb_controller.py                 -> abre a interface no navegador
  python rgb_controller.py aplicar gta6    -> aplica um preset (busca por parte do nome)
  python rgb_controller.py aplicar "#FF2E88 #9B3DFF 00D9C8" [--brilho 80] [--modo gradiente|alternado|zona] [--gravar]
  python rgb_controller.py claude perfil.json   (ou JSON pelo stdin com "-") -> perfil de cores feito por IA
  python rgb_controller.py listar          -> mostra dispositivos e zonas detectados
  python rgb_controller.py desligar
"""
import json
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))  # biblioteca openrgb-python instalada dentro da pasta do app
PALETTES_FILE = HERE / "palettes.json"
STATE_FILE = HERE / "last_state.json"
CLAUDE_FILE = HERE / "claude_color.json"
OPENRGB_EXE = HERE.parent / "OpenRGB" / "OpenRGB Windows 64-bit" / "OpenRGB.exe"
APP_NAME = "MeuRGB"
VERSION = "1.0.0"
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
    args = "--server --startminimized --noautoconnect"
    ps = (f"Start-Process -FilePath '{OPENRGB_EXE}' -ArgumentList '{args}' -Verb RunAs "
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


def device_info():
    c = client(refresh=True, autostart=False)
    return [{"id": i, "name": d.name, "type": dev_type(d),
             "modes": [m.name for m in d.modes],
             "zones": [{"name": z.name, "leds": len(z.leds)} for z in d.zones]}
            for i, d in enumerate(c.devices)]


def apply(palette, brightness=100, mode="gradiente", devices=None, save=False, offset=0.0, fast=False,
          overrides=None, groups=None, persist=True, ui=None):
    """Envia as cores para o hardware.
    devices: ids incluídos (None = todos) | overrides: {"<id>": {"<zona>": "#RRGGBB"}}
    persist=False: só pré-visualização (não grava o estado salvo do app)."""
    if not palette:
        raise ValueError("Paleta vazia")
    from openrgb.utils import RGBColor
    for attempt in (1, 2):
        try:
            c = client()
            devs = c.devices
            ids = [i for i in range(len(devs)) if devices is None or i in devices]
            plan = plan_colors(devs, ids, palette, mode, offset, overrides, groups)
            report = []
            with _lock:
                for idx in ids:
                    dev, cols = devs[idx], plan.get(idx) or []
                    if not cols:
                        continue
                    try:
                        if not fast:
                            prepare_device(dev)
                        dev.set_colors([RGBColor(*scale(x, brightness)) for x in cols], fast=fast)
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
            "devices": devices, "overrides": overrides or {}, "groups": groups or [], "ui": ui or {}},
            ensure_ascii=False), encoding="utf-8")
    return report


def turn_off():
    c = client()
    with _lock:
        for dev in c.devices:
            try:
                dev.off()
            except Exception:
                pass


# ---------------------------------------------------------------- efeito "fluir"
def start_effect(palette, brightness, mode, devices, speed, overrides=None, groups=None):
    stop_effect()
    ev = threading.Event()
    _effect["stop"] = ev

    def run():
        apply(palette, brightness, mode, devices, overrides=overrides, groups=groups, persist=False)
        t0 = time.time()
        while not ev.is_set():
            off = ((time.time() - t0) * speed / 20.0) % 1.0
            try:
                apply(palette, brightness, mode, devices, offset=off or 1e-6, fast=True,
                      overrides=overrides, groups=groups, persist=False)
            except Exception:
                pass
            ev.wait(0.08)

    th = threading.Thread(target=run, daemon=True)
    _effect.update(thread=th, on=True)
    th.start()


def stop_effect():
    _effect["stop"].set()
    th = _effect.get("thread")
    if th and th.is_alive() and th is not threading.current_thread():
        th.join(timeout=2)
    _effect.update(thread=None, on=False)


# ---------------------------------------------------------------- presets
def load_palettes():
    try:
        return json.loads(PALETTES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_palettes(p):
    PALETTES_FILE.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")


def find_preset(name):
    def norm(s):
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
            zq = str(z.get("zone", "")).strip().lower()
            for zi, zone in enumerate(devs[di].zones):
                if not zq or zq == str(zi) or zq in zone.name.lower():
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
    return ids, overrides, groups, links


def apply_claude(p, allow_effect=True):
    pal = parse_colors(p.get("colors", []))
    if not pal:
        raise ValueError("Perfil Claude Color sem cores")
    devs = client(refresh=True).devices
    ids, overrides, groups, links = resolve_profile(p, devs)
    stop_effect()
    bri, mode = int(p.get("brightness", 100)), p.get("mode", "gradiente")
    rep = apply(pal, bri, mode, ids, bool(p.get("save")), overrides=overrides, groups=groups,
                ui={"links": links} if links else None)
    if allow_effect and p.get("fluir"):
        start_effect(pal, bri, mode, ids, float(p.get("speed", 3)), overrides, groups)
    prof = dict(p, colors=[to_hex(c) for c in pal], created=time.strftime("%Y-%m-%d %H:%M:%S"))
    data = load_claude()
    hist = [h for h in data.get("history", []) if h.get("name") != prof.get("name")]
    CLAUDE_FILE.write_text(json.dumps({"active": prof, "history": ([prof] + hist)[:20]}, indent=2,
                                      ensure_ascii=False), encoding="utf-8")
    return rep, prof


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
        if self.path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html")
        if self.path == "/api/state":
            st = {"app": APP_NAME, "version": VERSION, "palettes": load_palettes(), "effect": _effect["on"],
                  "connected": openrgb_running(), "devices": [], "last": None, "claude": load_claude()}
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
            return self._send(200, st)
        if self.path == "/api/claude":
            return self._send(200, dict(load_claude(), effect=_effect["on"]))
        self._send(404, {"error": "não encontrado"})

    def do_POST(self):
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
                            persist=self.path == "/api/apply", ui=body.get("ui"))
                return self._send(200, {"ok": True, "report": rep})
            if self.path == "/api/effect":
                if body.get("on"):
                    start_effect(parse_colors(body.get("colors", [])), int(body.get("brightness", 100)),
                                 body.get("mode", "gradiente"), body.get("devices"), float(body.get("speed", 3)),
                                 body.get("overrides"), body.get("groups"))
                else:
                    stop_effect()
                return self._send(200, {"ok": True, "effect": _effect["on"]})
            if self.path == "/api/off":
                stop_effect()
                turn_off()
                return self._send(200, {"ok": True})
            if self.path == "/api/claude":
                rep, prof = apply_claude(body)
                return self._send(200, {"ok": True, "report": rep, "profile": prof, "effect": _effect["on"]})
            if self.path == "/api/preset":
                p = load_palettes()
                name = (body.get("name") or "").strip()
                if body.get("delete"):
                    p.pop(name, None)
                elif name:
                    p[name] = [to_hex(c) for c in parse_colors(body.get("colors", []))]
                save_palettes(p)
                return self._send(200, {"ok": True, "palettes": p})
        except Exception as e:
            return self._send(500, {"ok": False, "error": str(e)})
        self._send(404, {"error": "não encontrado"})


def serve():
    url = f"http://127.0.0.1:{UI_PORT}/"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", UI_PORT), Handler)
    except OSError:  # já tem um MeuRGB aberto: só abre a página dele
        print(f"O {APP_NAME} já está aberto, abrindo no navegador...")
        webbrowser.open(url)
        return
    print(f"{APP_NAME} v{VERSION} rodando em {url}  (Ctrl+C para sair)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------- CLI
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
    if cmd == "listar":
        client()
        for d in device_info():
            print(f"[{d['id']}] {d['name']} ({d['type']}) modos={d['modes']}")
            for z in d["zones"]:
                print(f"     - {z['name']}: {z['leds']} LEDs")
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
    elif cmd == "claude":
        src = argv[1] if len(argv) > 1 else "-"
        raw = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
        prof = json.loads(raw)
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
        print(f"Claude Color aplicado ({via}): {prof.get('name')} -> {' '.join(prof.get('colors', []))}")
        _print_report(rep)
    else:
        print(__doc__)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--no-browser"]
    if args:
        cli(args)
    else:
        serve()
