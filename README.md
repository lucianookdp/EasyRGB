<p align="center"><img src="docs/icon.png" width="96" alt="EasyRGB"></p>

<h1 align="center">EasyRGB</h1>

<p align="center"><b>All your PC's RGB in one light app. Install, pick your colors, done.</b></p>

<p align="center">
  Free, open-source <b>RGB controller for Windows</b> built on <a href="https://openrgb.org">OpenRGB</a>.<br>
  Motherboard, RAM, keyboard and other RGB gear in one place: a lightweight alternative to<br>
  ASRock Polychrome, ASUS Aura Sync / Armoury Crate, MSI Mystic Light and Gigabyte RGB Fusion.
</p>

<p align="center">
  <a href="../../releases/latest/download/EasyRGB-Setup.exe"><img alt="Download EasyRGB-Setup.exe" src="https://img.shields.io/badge/Download-EasyRGB--Setup.exe-a78bfa?style=for-the-badge&logo=windows&logoColor=white"></a>
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-1.2-a78bfa?style=flat-square">
  <img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?style=flat-square">
  <img alt="OpenRGB" src="https://img.shields.io/badge/OpenRGB-1.1-22c55e?style=flat-square">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-server-22c55e?style=flat-square">
  <img alt="MIT" src="https://img.shields.io/badge/license-MIT-71717a?style=flat-square">
</p>

<p align="center"><sub>English · <a href="#resumo-em-português">Resumo em português</a> · The app follows your Windows language.</sub></p>

<p align="center">
  <img src="docs/screenshot.png" alt="EasyRGB: palette, presets, computer and peripherals, each with its own effect" width="920">
</p>

## Install

1. **[Download EasyRGB-Setup.exe](../../releases/latest/download/EasyRGB-Setup.exe)** and run it.
2. Accept the Windows administrator prompt once (it installs the RGB driver).
3. EasyRGB opens in its own window and shows the RGB parts it found. Pick your colors. That's it.

No Python, no extra downloads: OpenRGB and its driver come inside the installer. It installs for your user only,
adds Start menu and desktop shortcuts, restores your colors when the PC starts, and **updates itself** with one click.
Remove it from *Settings → Apps → EasyRGB*.

> [!TIP]
> The installer isn't code-signed yet, so Windows SmartScreen may say *"Windows protected your PC"*.
> Click **More info → Run anyway**. Every file is built in the open by [GitHub Actions](../../actions) from this source.

Prefer no installer? Download **EasyRGB-windows.zip** from [Releases](../../releases/latest), extract it and open
`EasyRGB.exe`.

## What you get

| | |
|---|---|
| **Computer & peripherals** | **Computer** (motherboard, RAM, strips, coolers) and one card per **peripheral** (e.g. *Keyboard – Logitech G PRO*), each with its own effect, brightness and speed. |
| **Effects** | **Color wave** in your colors, Breathe, Color cycle, Rainbow, Flow and Music. Keyboards also get **Key ripple**, **Starlight** and **Screen color**, using each key's real position. Plus each chip's built-in effects. |
| **Live preview** | Your PC changes while you pick a color; then **Apply** or **Discard**. |
| **Per-zone & per-key colors** | Give any zone or key group (WASD, arrows, F-keys...) its own color. RAM sticks separate, mirrored or continuous. |
| **Works with brand apps** | No fighting Logitech G HUB: EasyRGB paints the keyboard through G HUB's own SDK, with G HUB open. **Beta:** Razer Synapse, Corsair iCUE and SteelSeries GG. |
| **Game mode** | **Find my games** reads Steam, Epic, GOG, Ubisoft, Xbox, EA, Riot and Battle.net; each game can switch to its own preset. |
| **Schedules & shortcuts** | Night mode dims at night and restores in the morning. Global shortcuts you choose yourself. |
| **Presets & sharing** | 13 built-in presets (GTA VI, Cyberpunk 2077, Valorant, Synthwave...) plus your own. Share looks with `EASYRGB1-...` codes and the [community gallery](GALLERY.md). |
| **Backup & undo** | Export your settings to a file and import them on another PC. **Undo everything** (with two confirmations) puts the PC back the way it was. |
| **Light** | About 50 MB in the background, near 0% CPU with static colors, tray icon next to the clock. |
| **Your language** | English and Portuguese built in, installer in 30 languages, and any other language translated for you by an AI (*How to use → Translate with AI*). |

## Extras with AI (optional)

You never need AI to use EasyRGB, but it makes some things faster.

**Change your lights by chatting.** In EasyRGB open *How to use → Connect an AI* and click **Connect** next to
your AI. One click works for **Claude Desktop, Claude Code, Cursor, GitHub Copilot (VS Code), Windsurf, Gemini CLI,
Codex and LM Studio**. Then just ask: *"make everything purple"*, *"keyboard wave in GTA VI colors"*,
*"dim to 30%"*, *"lights off"*. Using another app with MCP? *Other AI* shows the settings to copy
(command `EasyRGB.exe`, argument `--mcp`).

**Ask an AI for colors.** The **Ask AI for colors** button copies a ready-made request: paste it into any AI chat,
describe a mood, and the AI creates the look for your exact hardware.

<details>
<summary><b>Let an AI agent set up everything from source</b></summary>

EasyRGB is also an **almost-ready template**: an AI agent reads [`AGENTS.md`](AGENTS.md), installs everything,
detects your hardware and configures it for *your* PC, asking only which colors you like.

1. Download this repo (**Code → Download ZIP**) and extract it, e.g. to `C:\EasyRGB`.
2. Open an AI agent that can run commands (Claude Code, Codex, Gemini CLI, Cursor...) **in that folder** and paste:

```text
Set up EasyRGB on my PC following the AGENTS.md file in this folder. Do everything yourself, quickly (I'll accept the Windows administrator prompt). Only ask me which color style I like. When done, open the app and tell me in a few lines what you set up. I'll pick the effect later in the app. Answer in my language (if unsure, use my Windows language).
```

The prompt is also in [`START-HERE.txt`](START-HERE.txt) (English and Portuguese).
</details>

<details>
<summary><b>Run from source, commands and tests</b></summary>

**Requirements:** Windows 10/11, [OpenRGB-supported](https://openrgb.org/devices.html) hardware and
[Python 3](https://www.python.org/downloads/). Run `EasyRGB.bat`: the first time it installs official OpenRGB 1.1,
the Python libraries (per Python version) and the PawnIO driver, and disables (without deleting) the ASRock
Polychrome startup task. Undo with `Voltar para ASRock (admin).ps1`.

```bash
cd app
python rgb_controller.py detectar            # PC report (JSON) for the AI
python rgb_controller.py configurar pc.json  # save the PC profile
python rgb_controller.py ia look.json        # apply an AI-made look
python rgb_controller.py listar              # devices, zones and chip effects
python rgb_controller.py automacao rules.json
python rgb_controller.py iniciar-com-windows sim
python rgb_controller.py backup / restaurar  # save or restore every setting
python rgb_controller.py autoteste           # checks libraries, audio, screen capture and resources
python mcp_server.py                         # MCP server over stdio
cd ..
python -m unittest discover -s tests -v      # 134 tests, no hardware needed
python tools/build_exe.py                    # builds EasyRGB.exe, zip and EasyRGB-Setup.exe (CI does this on every push)
```

The same commands work as `EasyRGB.exe <command>` in the installed app.
</details>

## Help test your hardware

EasyRGB is fully tested on ASRock motherboards, Kingston FURY RAM and Logitech G keyboards. Razer, Corsair and
SteelSeries work through their own apps (beta), and OpenRGB supports hundreds of other devices: ASUS Aura, MSI
Mystic Light, Gigabyte RGB Fusion, HyperX, NZXT, Cooler Master, Thermaltake, Lian Li, Roccat, Redragon and more.

If you own any of these, a 2-minute test helps everyone:
1. Install EasyRGB and pick a color and an effect for each device.
2. Open a [hardware test report](../../issues/new?template=hardware-test.yml) and tell us what worked.

Something broke? In the same report, paste the result of `EasyRGB.exe diagnostico` (no personal data in it).

## Resumo em português

O **EasyRGB** controla todo o RGB do PC (placa-mãe, memórias, teclado e outros) num app leve e grátis, em cima do
OpenRGB.

1. **[Baixe o EasyRGB-Setup.exe](../../releases/latest/download/EasyRGB-Setup.exe)** e rode.
2. Aceite o pedido de administrador do Windows uma vez (é o driver de RGB).
3. O EasyRGB abre na própria janela com as peças que encontrou. Escolha as cores e pronto.

O OpenRGB e o driver já vêm dentro, nada mais é baixado. O app volta as suas cores quando o PC liga e se atualiza
sozinho. Se o Windows mostrar *"O Windows protegeu o computador"*, clique em **Mais informações → Executar assim mesmo**.

A tela separa **Computador** e **Periféricos** (ex.: *Teclado – Logitech G PRO*), cada um com o próprio efeito,
brilho e velocidade. Tem modo jogo que acha seus jogos sozinho, modo noite, atalhos que você escolhe, backup das
configurações e **Desfazer tudo**. A IA é opcional: em *Como usar → Conectar a uma IA*, um clique liga o EasyRGB ao
Claude, Cursor, GitHub Copilot, Windsurf, Gemini CLI ou Codex, e aí é só pedir as cores pelo chat.

Tem um periférico de outra marca (Razer, Corsair, ASUS, MSI, HyperX...)? Teste e conte como foi num
[relatório de teste](../../issues/new?template=hardware-test.yml).

---

<p align="center"><sub>Built on <a href="https://openrgb.org">OpenRGB</a>, <a href="https://github.com/namazso/PawnIO.Setup">PawnIO</a> and <a href="https://github.com/jath03/openrgb-python">openrgb-python</a>. Use at your own risk. MIT license.</sub></p>
