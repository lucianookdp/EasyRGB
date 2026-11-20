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


def main():
    if not PY.exists():
        run(sys.executable, "-m", "venv", VENV)
    run(PY, "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", *REQS)
    sep = ";"
    args = [PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "EasyRGB",
            "--icon", APP / "icon.ico", "--distpath", DIST, "--workpath", BUILD / "pyi", "--specpath", BUILD,
            "--paths", APP, "--hidden-import", "pystray._win32", "--hidden-import", "mcp_server",
            "--hidden-import", "vendors", "--collect-submodules", "comtypes", "--collect-submodules", "pycaw"]
    for r in RESOURCES:
        args += ["--add-data", f"{APP / r}{sep}."]
    run(*args, APP / "rgb_controller.py")
    out = DIST / "EasyRGB"
    for f in EXTRAS:
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, out / f)
    (out / "app").mkdir(exist_ok=True)   # dados de cada PC (estado, perfil, presets) ficam aqui
    z = DIST / "EasyRGB-windows.zip"
    if z.exists():
        z.unlink()
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in out.rglob("*"):
            zf.write(p, Path("EasyRGB") / p.relative_to(out))
    print(f"\nOK: {out / 'EasyRGB.exe'}\n    {z} ({z.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
