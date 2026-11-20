# Packaging: winget and code signing

Notes for the maintainer. Nothing here runs by itself.

## winget (`winget install lucianookdp.EasyRGB`)

1. Publish the release first (the CI attaches `EasyRGB-Setup.exe`).
2. Download that exact `EasyRGB-Setup.exe` and run
   `python tools/winget_manifest.py <version> path/to/EasyRGB-Setup.exe`.
   It writes `packaging/winget/<version>/` (version, installer and locale manifests, with the SHA-256).
3. Check it locally: `winget validate packaging/winget/<version>` and
   `winget install --manifest packaging/winget/<version>` (needs `winget settings --enable LocalManifestFiles`).
4. Submit: `wingetcreate submit packaging/winget/<version>` (opens the PR to microsoft/winget-pkgs), or fork
   winget-pkgs and add the folder under `manifests/l/lucianookdp/EasyRGB/<version>/`.
5. Later versions: `wingetcreate update lucianookdp.EasyRGB --version <v> --urls <Setup url> --submit`.

Unsigned installers are accepted, but Microsoft's validation may flag them for manual review.

## Code signing (removes the SmartScreen "Unknown publisher" warning)

- **SignPath Foundation** (free for open-source): apply at signpath.org with the public repo. They sign builds
  made by GitHub Actions, so the release workflow gets a signing step that uploads the exe and Setup and waits for
  the signed files. Requirements: OSI license (MIT ok), reproducible CI build, a code-signing policy in the README.
- **Azure Trusted Signing** (paid, about US$10/month): needs identity validation (individual or company with
  3+ years of history). Signs with `signtool` + the Trusted Signing dlib inside the workflow.
- **Classic OV/EV certificate** (US$200-400/year, hardware token): works, but is the most expensive and hardest
  to use in CI.

Sign both `EasyRGB.exe` (before Inno Setup packs it) and `EasyRGB-Setup.exe` (Inno's `SignTool=` directive).
SmartScreen reputation still grows with downloads, but signed files build it much faster.
