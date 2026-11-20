"""Acha os jogos instalados no PC lendo o que cada loja registra (não só uma lista fixa de jogos).

Steam (manifests de cada biblioteca), Epic (manifests .item), GOG e Ubisoft (registro do Windows), EA app e
Xbox / Microsoft Store (pastas e MicrosoftGame.config), Riot e Battle.net. Para cada jogo, escolhe o executável
principal (ignora instalador, launcher, anti-cheat, crash reporter...). Rápido: só olha a pasta de cada jogo.
"""
import json
import os
import re
import time
from pathlib import Path

# executáveis que não são o jogo
_SKIP = re.compile(r"unins|setup|install|redist|vcredist|vc_redist|dxsetup|directx|dotnet|crash|report|launcher|"
                   r"helper|updat|patch|easyanticheat|eac|battleye|beservice|cef|webhelper|server|editor|benchmark|"
                   r"config|settings|prereq|ue4prereq|ueprereq|cleanup|repair|register|uploader|overlay|tool|"
                   r"activation|touchup|cleanup|unitycrash|eosbootstrap|start_protected", re.I)
# o que a Steam instala mas não é jogo
_NOT_GAMES = re.compile(r"redistributable|steamworks|steamvr|proton|steam linux runtime|wallpaper engine|"
                        r"soundtrack|dedicated server|sdk|benchmark|demo$|driver booster|lossless scaling|blender|"
                        r"rpg maker|fl studio|soundpad|voicemod|aseprite|krita|vtube|obs studio|3dmark|furmark|"
                        r"cpu-z|gpu-z|msi afterburner|playtest", re.I)
_cache = {"t": 0.0, "v": None}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def pick_exe(folder, name="", depth=4):
    """Executável principal de uma pasta de jogo (o mais provável, pela pontuação)."""
    folder = Path(folder)
    if not folder.is_dir():
        return None
    base, best, best_score = len(folder.parts), None, -1e9
    want = _norm(name)
    for dirpath, dirnames, filenames in os.walk(folder):
        if len(Path(dirpath).parts) - base >= depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if not _SKIP.search(d) and not d.startswith(".")]
        for f in filenames:
            if not f.lower().endswith(".exe") or _SKIP.search(f[:-4]):
                continue
            p = Path(dirpath) / f
            stem = _norm(f[:-4].replace("Win64-Shipping", "").replace("-Win64-Shipping", ""))
            score = 0.0
            if "shipping" in f.lower():
                score += 4
            if want and stem and (stem in want or want in stem):
                score += 6
            if "binaries" in dirpath.lower() and "win64" in dirpath.lower():
                score += 2
            try:
                score += min(4.0, p.stat().st_size / 50e6)   # o jogo costuma ser o executável maior
            except OSError:
                pass
            score -= (len(Path(dirpath).parts) - base) * 0.3
            if score > best_score:
                best, best_score = p, score
    return best


def _vdf_paths(vdf):
    try:
        return [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text("utf-8", "ignore"))]
    except OSError:
        return []


def steam_games():
    roots = [Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"]
    roots += _vdf_paths(roots[0] / "steamapps" / "libraryfolders.vdf")
    for lib in dict.fromkeys(roots):
        apps = lib / "steamapps"
        for acf in apps.glob("appmanifest_*.acf"):
            try:
                txt = acf.read_text("utf-8", "ignore")
            except OSError:
                continue
            name = (re.search(r'"name"\s+"([^"]+)"', txt) or [None, ""])[1]
            inst = (re.search(r'"installdir"\s+"([^"]+)"', txt) or [None, ""])[1]
            if name and inst and not _NOT_GAMES.search(name):
                yield name, apps / "common" / inst, "Steam"


def epic_games():
    man = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    for item in man.glob("*.item"):
        try:
            j = json.loads(item.read_text("utf-8", "ignore"))
        except (OSError, ValueError):
            continue
        cats = [str(c).lower() for c in j.get("AppCategories", [])]
        if cats and "games" not in cats:
            continue
        loc, exe = j.get("InstallLocation"), j.get("LaunchExecutable")
        if loc:
            yield j.get("DisplayName") or Path(loc).name, Path(loc), "Epic", (Path(loc) / exe) if exe else None


def _reg_subkeys(root, path):
    try:
        import winreg
        with winreg.OpenKey(root, path) as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                name = winreg.EnumKey(k, i)
                with winreg.OpenKey(k, name) as sk:
                    vals = {}
                    for j in range(winreg.QueryInfoKey(sk)[1]):
                        n, v, _ = winreg.EnumValue(sk, j)
                        vals[n] = v
                    yield name, vals
    except OSError:
        return


def registry_games():
    import winreg
    hk = winreg.HKEY_LOCAL_MACHINE
    for _, v in _reg_subkeys(hk, r"SOFTWARE\WOW6432Node\GOG.com\Games"):   # GOG
        if v.get("path"):
            exe = Path(v["path"]) / v["exe"] if v.get("exe") else None
            yield v.get("gameName") or Path(v["path"]).name, Path(v["path"]), "GOG", exe
    for _, v in _reg_subkeys(hk, r"SOFTWARE\WOW6432Node\Ubisoft\Launcher\Installs"):   # Ubisoft Connect
        if v.get("InstallDir"):
            p = Path(v["InstallDir"])
            yield p.name, p, "Ubisoft", None
    for root in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                 r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):   # Battle.net e EA
        for _, v in _reg_subkeys(hk, root):
            pub = str(v.get("Publisher", ""))
            if re.search(r"blizzard|electronic arts|riot games", pub, re.I) and v.get("InstallLocation"):
                name = str(v.get("DisplayName", ""))
                if re.search(r"battle\.net|ea app|origin|riot client|vanguard", name, re.I):
                    continue
                yield name, Path(v["InstallLocation"]), pub.split()[0], None


def folder_games():
    for drive in ("C:", "D:", "E:", "F:"):
        xbox = Path(drive + "\\XboxGames")
        for g in (xbox.iterdir() if xbox.exists() else []):   # Xbox / Microsoft Store
            cfg = g / "Content" / "MicrosoftGame.config"
            exe = None
            try:
                m = re.search(r'<Executable\s+Name="([^"]+)"', cfg.read_text("utf-8", "ignore"))
                exe = g / "Content" / m.group(1) if m else None
            except OSError:
                pass
            yield g.name, g / "Content", "Xbox", exe
    for ea in (Path(r"C:\Program Files\EA Games"), Path(r"C:\Program Files (x86)\Origin Games")):
        for g in (ea.iterdir() if ea.exists() else []):
            if g.is_dir():
                yield g.name, g, "EA", None
    riot = Path(r"C:\Riot Games")
    for name, rel in (("VALORANT", r"VALORANT\live\ShooterGame\Binaries\Win64\VALORANT-Win64-Shipping.exe"),
                      ("League of Legends", r"League of Legends\Game\League of Legends.exe")):
        if (riot / rel).exists():
            yield name, riot / rel.split("\\")[0], "Riot", riot / rel


def find_games(known=None, force=False):
    """Lista [{"name", "process", "path", "source", "preset"}] dos jogos instalados (cache de 10 min)."""
    if not force and _cache["v"] is not None and time.time() - _cache["t"] < 600:
        return _cache["v"]
    known = {k.lower(): (k, v) for k, v in (known or {}).items()}
    found = {}

    def add(name, folder, source, exe=None):
        exe = Path(exe) if exe and Path(exe).exists() else None
        if not exe and folder:
            # um executável conhecido na pasta ganha de tudo (ex.: o GTA tem vários .exe)
            exe = next((Path(dp) / f for dp, _, fs in os.walk(folder) for f in fs if f.lower() in known), None) \
                if Path(folder).is_dir() else None
            exe = exe or pick_exe(folder, name)
        if not exe:
            return
        if any(_norm(v["name"]) == _norm(name) for v in found.values()):
            return   # o mesmo jogo por outra loja (ex.: VALORANT pela Epic e pela Riot)
        proc = exe.name
        k = known.get(proc.lower())
        found.setdefault(proc.lower(), {"name": str(name).strip(), "process": k[0] if k else proc,
                                         "path": str(exe), "source": source, "preset": k[1] if k else ""})

    for name, folder, source in _safe(steam_games):
        add(name, folder, source)
    for gen in (folder_games, registry_games, epic_games):   # Riot/Xbox antes da Epic (que lista launchers)
        for name, folder, source, exe in _safe(gen):
            add(name, folder, source, exe)
    out = sorted(found.values(), key=lambda g: g["name"].lower())
    _cache.update(t=time.time(), v=out)
    return out


def _safe(gen):
    try:
        yield from gen()
    except Exception:
        return
