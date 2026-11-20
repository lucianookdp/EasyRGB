<p align="center"><img src="docs/icon.png" width="96" alt="EasyRGB"></p>

<h1 align="center">EasyRGB</h1>

<p align="center"><b>Your PC's RGB, set up by AI.</b></p>

<p align="center">
  Free, open-source <b>RGB controller for Windows</b> built on <a href="https://openrgb.org">OpenRGB</a>.<br>
  One app for your motherboard, RAM, keyboard and other RGB devices: a lightweight alternative to<br>
  ASRock Polychrome, ASUS Aura Sync / Armoury Crate, MSI Mystic Light and Gigabyte RGB Fusion.
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-v1-a78bfa?style=flat-square">
  <img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?style=flat-square&logo=windows&logoColor=white">
  <img alt="Python" src="https://img.shields.io/badge/Python-3-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="OpenRGB" src="https://img.shields.io/badge/OpenRGB-1.1-22c55e?style=flat-square">
  <img alt="MIT" src="https://img.shields.io/badge/license-MIT-71717a?style=flat-square">
</p>

<p align="center"><sub>English · <a href="#resumo-em-português">Resumo em português</a> · The app follows your system language (English or Portuguese).</sub></p>

<p align="center">
  <img src="docs/screenshot.png" alt="EasyRGB" width="920">
</p>

> [!NOTE]
> **Version 1 (V1).** First public release. It works day to day, but it will still change a lot.

## Start here

EasyRGB is a **template**: an AI agent installs it and adapts it to *your* PC (devices, chip effects, conflicts) **before you even open it**. No technical knowledge needed.

1. Download this repo (**Code → Download ZIP**) and extract it, e.g. to `C:\EasyRGB`.
2. Open an AI agent that can run commands on your PC (Claude Code, Codex, Gemini CLI, Cursor...) **in that folder**.
3. Paste this prompt and answer its questions (Windows asks for administrator permission once: click **Yes**):

```text
Set up EasyRGB, my PC's RGB controller. Read the AGENTS.md file in this folder and follow it. Talk to me in English.
If it isn't installed yet, install it first (I'll accept the Windows administrator prompt).
Detect my hardware and tell me in a few words what you found.
Then ask me what you need, one question at a time with options to pick from: style or game I like, which devices to apply it to, how to set the RAM sticks, any effect, game mode, night mode and whether to restore colors when the PC starts.
Finally, set up and apply everything and show me a short summary.
```

4. Done. Open **`EasyRGB.bat`** whenever you want to change things yourself, or just ask the agent for a new look.

The same prompt (also in Portuguese) is in [`START-HERE.txt`](START-HERE.txt), and the app has a **Copy setup prompt** button. `EasyRGB.bat` reminds you if the PC hasn't been set up by AI yet.

## Features

| | |
|---|---|
| **AI setup** | The agent detects motherboard, BIOS, RAM, GPU, peripherals, each chip's built-in effects and conflicting vendor apps, then configures everything. Instructions live in [`AGENTS.md`](AGENTS.md). |
| **AI looks** | *"Purple and blue cyberpunk, white keyboard, continuous RAM"*: the agent builds and applies it. The **AI colors** button copies the prompt in one click. |
| **Live preview** | Your PC changes while you pick a color, then **Apply** or **Discard**. |
| **Computer & peripherals** | One clear screen: **Computer** (motherboard, RAM, strips, coolers) and **Peripherals**, one block per device (e.g. *Keyboard – Logitech G PRO*). Each can follow the palette or not, and run **its own effect**: computer still, keyboard in a color wave. |
| **Works on top of vendor apps** | No more fighting Logitech G HUB: EasyRGB paints your Logitech keyboard key by key through G HUB's own lighting SDK, with G HUB still open. Close EasyRGB and G HUB goes back to its profile. The AI only enables what exists on *your* PC. |
| **Per-zone colors** | Give any zone its own color. RAM sticks can be separate, mirrored or continuous. |
| **Effects** | **Color wave** in your own colors (pick direction and speed), Breathe, Color cycle, Rainbow, Flow and Music for any device. Keyboard-only: **Key ripple**, **Starlight** and **Screen color**, using each key's real position. Plus each chip's native effects, read from your hardware. |
| **Game mode** | Open a game and the PC switches to its preset; close it and your look comes back. |
| **Night mode & schedules** | Dim at night, back to normal in the morning, presets at set times. |
| **Restore on PC start** | Brings colors back after a reboot (even on RAM that can't store them) and **exits by itself**: nothing stays in memory. |
| **Music, shortcuts & tray** | Lights that dance to what's playing, global Ctrl+Alt shortcuts, and a tray icon next to the clock (no window, ~35 MB). |
| **Keyboard highlights** | Color WASD, arrows, numbers, F-keys and more on their own. Warns when a vendor app with no bridge yet fights for your lights. |
| **Presets & gallery** | 13 built-in presets that never change, plus your own. Share looks with `EASYRGB1-...` codes and browse the [community gallery](GALLERY.md). |
| **English / Português** | Follows your system language. Dark theme, like most RGB apps, so LED colors look true. |

<details>
<summary><b>Manual install, commands and tests</b></summary>

**Requirements:** Windows 10/11, [Python 3](https://www.python.org/downloads/), [OpenRGB-supported](https://openrgb.org/devices.html) hardware.
Without an agent: run `EasyRGB.bat` and choose *Open anyway*. It installs official OpenRGB 1.1, the Python libraries (`openrgb-python`, Pillow, pystray, pycaw; reinstalled automatically if your Python version changes) and the signed PawnIO driver, and disables (without deleting) the ASRock Polychrome startup task. Undo with `Voltar para ASRock (admin).ps1`.

```bash
cd app
python rgb_controller.py detectar            # PC report (JSON) for the AI
python rgb_controller.py configurar pc.json  # save the PC profile
python rgb_controller.py ia look.json        # apply an AI-made look
python rgb_controller.py listar              # devices, zones and chip effects
python rgb_controller.py automacao rules.json
python rgb_controller.py iniciar-com-windows sim
python -m unittest discover -s tests -v      # 77 tests, no hardware needed
```
</details>

## Resumo em português

O **EasyRGB** controla o RGB do PC por paletas e é feito para ser **configurado por IA**. Baixe a pasta, abra um agente de IA nela (Claude Code, Codex, Gemini CLI...) e cole o prompt em português do [`START-HERE.txt`](START-HERE.txt). Ele instala, detecta a sua placa, RAMs e periféricos, faz as perguntas e deixa tudo pronto. Depois é só abrir o `EasyRGB.bat`.
A tela separa **Computador** e **Periféricos** (ex.: *Teclado – Logitech G PRO*), cada um com o próprio efeito, como a **onda de cores** com as suas cores. O EasyRGB pinta o teclado Logitech **por cima do G HUB**, sem conflito. O app fica em português ou inglês conforme o idioma do seu sistema.

---

<p align="center"><sub>Built on <a href="https://openrgb.org">OpenRGB</a>, <a href="https://github.com/namazso/PawnIO.Setup">PawnIO</a> and <a href="https://github.com/jath03/openrgb-python">openrgb-python</a>. Use at your own risk. MIT license.</sub></p>
