<p align="center"><img src="docs/icon.png" width="96" alt="EasyRGB"></p>

<h1 align="center">EasyRGB</h1>

<p align="center"><b>Your PC's RGB, set up by AI. Change it by chatting.</b></p>

<p align="center">
  Free, open-source <b>RGB controller for Windows</b> built on <a href="https://openrgb.org">OpenRGB</a>.<br>
  One light app for your motherboard, RAM, keyboard and other RGB gear: a lightweight alternative to<br>
  ASRock Polychrome, ASUS Aura Sync / Armoury Crate, MSI Mystic Light and Gigabyte RGB Fusion.
</p>

<p align="center">
  <a href="../../releases/latest"><img alt="Download" src="https://img.shields.io/badge/download-EasyRGB.exe-a78bfa?style=flat-square&logo=windows&logoColor=white"></a>
  <img alt="Version" src="https://img.shields.io/badge/version-1.1-a78bfa?style=flat-square">
  <img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?style=flat-square">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-server-22c55e?style=flat-square">
  <img alt="OpenRGB" src="https://img.shields.io/badge/OpenRGB-1.1-22c55e?style=flat-square">
  <img alt="MIT" src="https://img.shields.io/badge/license-MIT-71717a?style=flat-square">
</p>

<p align="center"><sub>English · <a href="#resumo-em-português">Resumo em português</a> · The app follows your system language (English or Portuguese).</sub></p>

<p align="center">
  <img src="docs/screenshot.png" alt="EasyRGB: colors, computer and peripherals, each with its own effect" width="920">
</p>

## Three ways to use it

| | For | What you do |
|---|---|---|
| **1. Download the app** | Anyone | Download, double-click `EasyRGB.exe`, pick colors. No Python, no setup. |
| **2. Chat with AI** | Claude Desktop, Claude Code, Cursor... | *"make my PC purple with a wave on the keyboard"* and the lights change. |
| **3. Let an AI agent set it up** | Claude Code, Codex, Gemini CLI... | Paste one prompt; the agent installs and configures everything for your PC. |

### 1. Download the app

1. Download **EasyRGB-windows.zip** from [Releases](../../releases/latest) and extract it (e.g. to `C:\EasyRGB`).
2. Open **`EasyRGB.exe`**. The first time, Windows asks for administrator permission once: it installs official
   OpenRGB and the signed PawnIO driver it uses to talk to your RGB chips.
3. Pick a preset or your own colors. Done.

> [!TIP]
> EasyRGB.exe isn't code-signed yet, so Windows SmartScreen may say *"Windows protected your PC"*.
> Click **More info → Run anyway**. Every exe is built in the open by [GitHub Actions](../../actions) from this source.

### 2. Change your lights by chatting (MCP)

EasyRGB ships an [MCP](https://modelcontextprotocol.io) server, so AI chat apps can change your lights:
*"make everything purple"*, *"keyboard wave in GTA VI colors"*, *"dim to 30%"*, *"lights off"*.

- **Claude Desktop:** in EasyRGB click **Use in Claude Desktop**, then restart Claude Desktop.
- **Claude Code:** `claude mcp add easyrgb -- C:\EasyRGB\EasyRGB.exe --mcp`
- **Cursor, VS Code and others:** a stdio server with command `C:\EasyRGB\EasyRGB.exe` and args `["--mcp"]`
  (from source: `python app/mcp_server.py`).

Tools: `easyrgb_status`, `easyrgb_apply_look`, `easyrgb_brightness`, `easyrgb_lights`.

### 3. Let an AI agent set it up

EasyRGB is also an **almost-ready template**: an AI agent reads [`AGENTS.md`](AGENTS.md), installs everything,
detects your hardware and configures it for *your* PC, asking only which colors you like. It answers in your language.

1. Download this repo (**Code → Download ZIP**) and extract it, e.g. to `C:\EasyRGB`.
2. Open an AI agent that can run commands (Claude Code, Codex, Gemini CLI, Cursor...) **in that folder** and paste:

```text
Set up EasyRGB on my PC following the AGENTS.md file in this folder. Do everything yourself, quickly (I'll accept the Windows administrator prompt). Only ask me which color style I like. When done, open the app and tell me in a few lines what you set up. I'll pick the effect later in the app. Answer in my language (if unsure, use my Windows language).
```

3. The app opens with your look applied. Pick effects there, or ask the agent for a new look anytime.

The prompt is also in [`START-HERE.txt`](START-HERE.txt) (English and Portuguese) and behind the app's **AI colors** button.

## Features

| | |
|---|---|
| **Computer & peripherals** | One clear screen: **Computer** (motherboard, RAM, strips, coolers) and **Peripherals**, one block per device (e.g. *Keyboard – Logitech G PRO*). Each can follow the palette or not and run **its own effect**: computer still, keyboard in a wave. |
| **Effects** | **Color wave** in your own colors (direction and speed), Breathe, Color cycle, Rainbow, Flow and Music. Keyboard-only: **Key ripple**, **Starlight** and **Screen color**, using each key's real position. Plus each chip's built-in effects, read from your hardware. |
| **Works with vendor apps** | No fighting Logitech G HUB: EasyRGB paints Logitech keyboards key by key through G HUB's own lighting SDK, with G HUB still open. It waits for G HUB at startup and reconnects if it restarts. |
| **AI everywhere** | Setup by any AI agent, looks described in words, and live control from AI chat apps (MCP). |
| **Live preview** | Your PC changes while you pick a color; then **Apply** or **Discard**. |
| **Per-zone & per-key colors** | Give any zone or key group (WASD, arrows, F-keys...) its own color. RAM sticks separate, mirrored or continuous. |
| **Game mode & schedules** | Open a game and the PC switches to its preset; night mode dims at night and restores in the morning. |
| **Restore on PC start** | Brings colors back after a reboot, even on RAM that forgets them, and closes itself when nothing needs to run. Survives Python updates. |
| **Light** | ~50 MB in the background, tray icon next to the clock, global Ctrl+Alt shortcuts, no heavy animations in the UI. |
| **Presets & sharing** | 13 built-in presets (GTA VI, Cyberpunk 2077, Valorant, Synthwave...) plus your own. Share looks with `EASYRGB1-...` codes and the [community gallery](GALLERY.md). |
| **Any screen, two languages** | Responsive down to phone width. English or Portuguese, following your system. Dark theme so LED colors look true. |

<details>
<summary><b>Run from source, commands and tests</b></summary>

**Requirements:** Windows 10/11 and [OpenRGB-supported](https://openrgb.org/devices.html) hardware.
From source you also need [Python 3](https://www.python.org/downloads/) (the `.exe` doesn't).
Run `EasyRGB.bat`: the first time it installs official OpenRGB 1.1, the Python libraries (per Python version,
reinstalled automatically if your Python changes) and the PawnIO driver, and disables (without deleting) the ASRock
Polychrome startup task. Undo with `Voltar para ASRock (admin).ps1`.

```bash
cd app
python rgb_controller.py detectar            # PC report (JSON) for the AI
python rgb_controller.py configurar pc.json  # save the PC profile
python rgb_controller.py ia look.json        # apply an AI-made look
python rgb_controller.py listar              # devices, zones and chip effects
python rgb_controller.py automacao rules.json
python rgb_controller.py iniciar-com-windows sim
python rgb_controller.py autoteste           # checks libraries, audio, screen capture and resources
python mcp_server.py                         # MCP server over stdio
cd ..
python -m unittest discover -s tests -v      # 84 tests, no hardware needed
python tools/build_exe.py                    # builds EasyRGB.exe + zip (CI does this on every push)
```

The same commands work as `EasyRGB.exe <command>` in the downloaded app.
</details>

## Resumo em português

O **EasyRGB** controla o RGB do PC (placa-mãe, memórias, teclado e outros) num app leve e grátis, em cima do OpenRGB.
Dá para usar de três jeitos:

1. **Baixar o app:** baixe o `EasyRGB-windows.zip` em [Releases](../../releases/latest), extraia e abra o
   `EasyRGB.exe`. Não precisa de Python. Na primeira vez o Windows pede administrador uma vez.
2. **Conversar com a IA:** clique em **Usar no Claude Desktop** e peça pelo chat, por exemplo *"deixa tudo roxo
   com onda no teclado"*. Também funciona no Claude Code, Cursor e outros apps com MCP.
3. **Deixar um agente de IA configurar:** abra um agente (Claude Code, Codex, Gemini CLI...) na pasta e cole o
   prompt em português do [`START-HERE.txt`](START-HERE.txt). Ele instala e configura tudo sozinho, só perguntando
   as cores que você curte.

A tela separa **Computador** e **Periféricos** (ex.: *Teclado – Logitech G PRO*), cada um com o próprio efeito,
como a **onda de cores** com as suas cores. O teclado Logitech é pintado **por cima do G HUB**, sem conflito.
O app fica em português ou inglês conforme o idioma do sistema.

---

<p align="center"><sub>Built on <a href="https://openrgb.org">OpenRGB</a>, <a href="https://github.com/namazso/PawnIO.Setup">PawnIO</a> and <a href="https://github.com/jath03/openrgb-python">openrgb-python</a>. Use at your own risk. MIT license.</sub></p>
