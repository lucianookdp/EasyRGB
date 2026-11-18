<p align="center"><img src="docs/logo.svg" width="84" alt="MeuRGB"></p>

<h1 align="center">MeuRGB</h1>

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
  <img src="docs/screenshot.png" alt="MeuRGB" width="920">
</p>

> [!NOTE]
> **Version 1 (V1).** First public release. It works day to day, but it will still change a lot.

## Start here

MeuRGB is a **template**: an AI agent installs it and adapts it to *your* PC (devices, chip effects, conflicts) **before you even open it**. No technical knowledge needed.

1. Download this repo (**Code → Download ZIP**) and extract it, e.g. to `C:\MeuRGB`.
2. Open an AI agent that can run commands on your PC (Claude Code, Codex, Gemini CLI, Cursor...) **in that folder**.
3. Paste this prompt and answer its questions (Windows asks for administrator permission once: click **Yes**):

```text
Set up MeuRGB, my PC's RGB controller. Read the AGENTS.md file in this folder and follow it. Talk to me in English.
If it isn't installed yet, install it first (I'll accept the Windows administrator prompt).
Detect my hardware and tell me in a few words what you found.
Then ask me what you need, one question at a time with options to pick from: style or game I like, which devices to apply it to, how to set the RAM sticks, any effect, game mode, night mode and whether to restore colors when the PC starts.
Finally, set up and apply everything and show me a short summary.
```

4. Done. Open **`MeuRGB.bat`** whenever you want to change things yourself, or just ask the agent for a new look.

The same prompt (also in Portuguese) is in [`START-HERE.txt`](START-HERE.txt), and the app has a **Copy setup prompt** button. `MeuRGB.bat` reminds you if the PC hasn't been set up by AI yet.

## Features

| | |
|---|---|
| **AI setup** | The agent detects motherboard, BIOS, RAM, GPU, peripherals, each chip's built-in effects and conflicting vendor apps, then configures everything. Instructions live in [`AGENTS.md`](AGENTS.md). |
| **AI looks** | *"Purple and blue cyberpunk, white keyboard, continuous RAM"*: the agent builds and applies it, with history in the app. |
| **Live preview** | Your PC changes while you pick a color, then **Apply** or **Discard**. |
| **Apply the palette to** | Choose which devices (motherboard, RAM, keyboard, any other) follow the palette. |
| **Per-zone colors** | Give any zone its own color. RAM sticks can be separate, mirrored or continuous. |
| **Effects** | App effects (Flow, Breathe, Color cycle, Rainbow) and each chip's native effects, read from your hardware. |
| **Game mode** | Open a game and the PC switches to its preset; close it and your look comes back. |
| **Night mode & schedules** | Dim at night, back to normal in the morning, presets at set times. |
| **Restore on PC start** | Brings colors back after a reboot (even on RAM that can't store them) and **exits by itself**: nothing stays in memory. |
| **14 presets & share codes** | Popular themes plus a few games you know by their colors; share looks with `MEURGB1-...` codes. |
| **English / Português** | Follows your system language. Dark theme, like most RGB apps, so LED colors look true. |

<details>
<summary><b>Manual install, commands and tests</b></summary>

**Requirements:** Windows 10/11, [Python 3](https://www.python.org/downloads/), [OpenRGB-supported](https://openrgb.org/devices.html) hardware.
Without an agent: run `MeuRGB.bat` and choose *Open anyway*. It installs official OpenRGB 1.1, `openrgb-python` and the signed PawnIO driver, and disables (without deleting) the ASRock Polychrome startup task. Undo with `Voltar para ASRock (admin).ps1`.

```bash
cd app
python rgb_controller.py detectar            # PC report (JSON) for the AI
python rgb_controller.py configurar pc.json  # save the PC profile
python rgb_controller.py ia look.json        # apply an AI-made look
python rgb_controller.py listar              # devices, zones and chip effects
python rgb_controller.py automacao rules.json
python rgb_controller.py iniciar-com-windows sim
python -m unittest discover -s tests -v      # 48 tests, no hardware needed
```
</details>

## Resumo em português

O **MeuRGB** controla o RGB do PC por paletas e é feito para ser **configurado por IA**. Baixe a pasta, abra um agente de IA nela (Claude Code, Codex, Gemini CLI...) e cole o prompt em português do [`START-HERE.txt`](START-HERE.txt). Ele instala, detecta a sua placa, RAMs e periféricos, faz as perguntas e deixa tudo pronto. Depois é só abrir o `MeuRGB.bat`. O app fica em português ou inglês conforme o idioma do seu sistema.

---

<p align="center"><sub>Built on <a href="https://openrgb.org">OpenRGB</a>, <a href="https://github.com/namazso/PawnIO.Setup">PawnIO</a> and <a href="https://github.com/jath03/openrgb-python">openrgb-python</a>. Use at your own risk. MIT license.</sub></p>
