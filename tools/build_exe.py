"""Builds EasyRGB.exe (no Python needed on the user's PC) and the download zip.

    python tools/build_exe.py

Output: dist/EasyRGB/ (EasyRGB.exe + files) and dist/EasyRGB-windows.zip
Uses its own virtual environment in build/venv, so nothing is installed into your Python.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
VENV = BUILD / "venv"
PY = VENV / "Scripts" / "python.exe"
REQS = ["pyinstaller", "openrgb-python", "pycaw", "comtypes", "pystray", "pillow"]
# arquivos que vão junto do EasyRGB.exe, na raiz da pasta baixada
EXTRAS = ["1-Configurar (admin).ps1", "Voltar para ASRock (admin).ps1", "AGENTS.md", "CLAUDE.md", "START-HERE.txt",
          "README.md", "GALLERY.md", "LICENSE"]
RESOURCES = ["index.html", "palettes.json", "icon.png", "icon.ico", "tray.png"]


def run(*cmd, **kw):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


OPENRGB_URL = "https://codeberg.org/OpenRGB/OpenRGB/releases/download/release_1.1/OpenRGB_1.1_Windows_64_8e16de2.zip"
NOTICE = """EasyRGB includes, unmodified, these programs made by others:

- OpenRGB 1.1 (folder OpenRGB) - GPL-2.0 - https://openrgb.org
  Source code: https://codeberg.org/OpenRGB/OpenRGB/src/tag/release_1.1
- PawnIO driver installer (download/PawnIO_setup.exe) - signed by its author - https://github.com/namazso/PawnIO.Setup

EasyRGB itself is MIT licensed (see LICENSE).
"""


def _download(url, dest):
    import urllib.request
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print("> baixando", url, flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "EasyRGB-build"})
    with urllib.request.urlopen(req, timeout=300) as r:
        dest.write_bytes(r.read())
    return dest


def bundle_openrgb(out):
    """Coloca o OpenRGB e o instalador do driver dentro do pacote: a primeira vez não depende de internet."""
    import json
    import urllib.request
    cache = BUILD / "cache"
    z = _download(OPENRGB_URL, cache / "OpenRGB_1.1.zip")
    with zipfile.ZipFile(z) as zf:
        zf.extractall(out / "OpenRGB")
    req = urllib.request.Request("https://api.github.com/repos/namazso/PawnIO.Setup/releases/latest",
                                 headers={"User-Agent": "EasyRGB-build", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rel = json.loads(r.read())
    url = next(a["browser_download_url"] for a in rel["assets"] if a["name"] == "PawnIO_setup.exe")
    pawn = _download(url, cache / f"PawnIO_setup_{rel.get('tag_name', 'latest')}.exe")
    (out / "download").mkdir(exist_ok=True)
    shutil.copy2(pawn, out / "download" / "PawnIO_setup.exe")
    (out / "THIRD-PARTY-NOTICES.txt").write_text(NOTICE, encoding="utf-8")


def _iscc():
    bases = [os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""),
             str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs")]
    for base in bases:
        p = Path(base) / "Inno Setup 6" / "ISCC.exe"
        if base and p.exists():
            return p
    found = shutil.which("iscc")
    return Path(found) if found else None


def build_installer(ver):
    """EasyRGB-Setup.exe com o Inno Setup (se estiver instalado; o GitHub Actions já tem)."""
    iscc = _iscc()
    if not iscc:
        print("    (Inno Setup não encontrado: instalador não gerado)")
        return None
    run(iscc, "/Qp", f"/DAppVersion={ver}", f"/DSourceDir={DIST / 'EasyRGB'}", f"/O{DIST}",
        ROOT / "installer" / "EasyRGB.iss")
    return DIST / "EasyRGB-Setup.exe"


def main():
    if not PY.exists():
        run(sys.executable, "-m", "venv", VENV)
    run(PY, "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", *REQS)
    sep = ";"
    # versão e descrição que aparecem em Propriedades > Detalhes do EasyRGB.exe
    ver = next(l.split('"')[1] for l in (APP / "rgb_controller.py").read_text(encoding="utf-8").splitlines()
               if l.startswith("VERSION = "))
    nums = tuple(int(x) for x in (ver.split(".") + ["0", "0", "0"])[:4])
    BUILD.mkdir(exist_ok=True)
    vfile = BUILD / "version.txt"
    vfile.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'EasyRGB (open source)'),
    StringStruct('FileDescription', 'EasyRGB - RGB controller set up by AI'),
    StringStruct('FileVersion', '{ver}'), StringStruct('InternalName', 'EasyRGB'),
    StringStruct('LegalCopyright', 'MIT license'), StringStruct('OriginalFilename', 'EasyRGB.exe'),
    StringStruct('ProductName', 'EasyRGB'), StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")
    args = [PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "EasyRGB",
            "--icon", APP / "icon.ico", "--version-file", vfile, "--distpath", DIST, "--workpath", BUILD / "pyi", "--specpath", BUILD,
            "--paths", APP, "--hidden-import", "pystray._win32", "--hidden-import", "mcp_server",
            "--hidden-import", "vendors", "--hidden-import", "vendors_more", "--hidden-import", "games", "--collect-submodules", "comtypes", "--collect-submodules", "pycaw"]
    for r in RESOURCES:
        args += ["--add-data", f"{APP / r}{sep}."]
    if (APP / "lang").exists():   # traduções extras que vierem no repositório
        args += ["--add-data", f"{APP / 'lang'}{sep}lang"]
    run(*args, APP / "rgb_controller.py")
    out = DIST / "EasyRGB"
    for f in EXTRAS:
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, out / f)
    (out / "app").mkdir(exist_ok=True)   # dados de cada PC (estado, perfil, presets) ficam aqui
    bundle_openrgb(out)
    z = DIST / "EasyRGB-windows.zip"
    if z.exists():
        z.unlink()
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in out.rglob("*"):
            zf.write(p, Path("EasyRGB") / p.relative_to(out))
    print(f"\nOK: {out / 'EasyRGB.exe'}\n    {z} ({z.stat().st_size / 1e6:.1f} MB)")
    setup = build_installer(ver)
    if setup:
        print(f"    {setup} ({setup.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
