"""Gera os manifestos do winget (packaging/winget/<versão>/) a partir do EasyRGB-Setup.exe de um release.

Uso:  python tools/winget_manifest.py [versão] [caminho-do-Setup.exe]
Sem caminho, usa dist/EasyRGB-Setup.exe. O hash precisa ser o do arquivo publicado no release (o mesmo binário).
Depois: fork de microsoft/winget-pkgs, copie a pasta para manifests/l/lucianookdp/EasyRGB/<versão>/ e abra o PR
(ou use `wingetcreate submit packaging/winget/<versão>`). Detalhes em packaging/README.md.
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ID = "lucianookdp.EasyRGB"
REPO = "https://github.com/lucianookdp/EasyRGB"
SCHEMA = "1.6.0"


def version_from_code():
    m = re.search(r'^VERSION = "([^"]+)"', (ROOT / "app" / "rgb_controller.py").read_text(encoding="utf-8"), re.M)
    return m.group(1)


def manifests(version, sha256):
    head = f"PackageIdentifier: {ID}\nPackageVersion: {version}\n"
    return {
        f"{ID}.yaml": f"{head}DefaultLocale: en-US\nManifestType: version\nManifestVersion: {SCHEMA}\n",
        f"{ID}.installer.yaml": f"""{head}InstallerType: inno
Scope: user
InstallModes: [interactive, silent, silentWithProgress]
UpgradeBehavior: install
ReleaseDate: null
Installers:
  - Architecture: x64
    InstallerUrl: {REPO}/releases/download/v{version}/EasyRGB-Setup.exe
    InstallerSha256: {sha256}
ManifestType: installer
ManifestVersion: {SCHEMA}
""".replace("ReleaseDate: null\n", ""),
        f"{ID}.locale.en-US.yaml": f"""{head}PackageLocale: en-US
Publisher: lucianookdp
PublisherUrl: https://github.com/lucianookdp
PackageName: EasyRGB
PackageUrl: {REPO}
License: MIT
LicenseUrl: {REPO}/blob/main/LICENSE
ShortDescription: Control all your PC RGB lights in one light app, set up by an AI agent. Built on OpenRGB.
Description: |-
  EasyRGB controls motherboard, RAM, keyboard and other RGB lights in one place, with per-device effects,
  game mode, schedules and hotkeys. An AI agent (or Claude Desktop via MCP) can set it up and create looks.
Tags: [rgb, openrgb, lighting, led, keyboard, gaming, mcp]
ReleaseNotesUrl: {REPO}/releases/tag/v{version}
ManifestType: defaultLocale
ManifestVersion: {SCHEMA}
""",
    }


def main(argv):
    version = argv[0] if argv else version_from_code()
    setup = Path(argv[1]) if len(argv) > 1 else ROOT / "dist" / "EasyRGB-Setup.exe"
    sha = hashlib.sha256(setup.read_bytes()).hexdigest().upper()
    out = ROOT / "packaging" / "winget" / version
    out.mkdir(parents=True, exist_ok=True)
    for name, text in manifests(version, sha).items():
        (out / name).write_text(text, encoding="utf-8")
    print("OK:", out)


if __name__ == "__main__":
    main(sys.argv[1:])
