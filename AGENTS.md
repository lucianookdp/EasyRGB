# EasyRGB: instructions for AI agents

For any agent that runs commands on the user's PC (Claude Code, Codex, Gemini CLI, Cursor, Copilot...).
The idea behind EasyRGB: **anything that can be automated, the agent does**: identify the hardware, configure it and
create the looks.

**Language:** always talk to the person in **their** language: the language of their message, or the Windows display
language if unclear. This file is in English so it works for everyone; never answer in English just because of it.
Translate preset and device names when it helps (e.g. "Placa-mãe" / "Motherboard").

EasyRGB is a palette-based RGB controller on top of OpenRGB 1.1 (SDK server on port 6742, runs as admin, PawnIO driver).
App in `app/rgb_controller.py` (local server + CLI), UI in `app/index.html` (http://127.0.0.1:6750), opened by
`EasyRGB.bat`. The UI follows the system language (English or Portuguese; `?lang=en|pt` forces one).
All commands below run inside the `app/` folder. CLI command names are Portuguese (`detectar`, `configurar`, `ia`...).

## 0. Quick setup (the prompt from `START-HERE.txt`, the README and the app's AI button)

EasyRGB is an **almost-ready template**: the person downloads the folder, opens you in it and pastes the prompt, often
before opening the app. They may not be technical. **Set up everything yourself, quickly, saying little.**
Only stop for steps marked *ask*. They pick the effect later, in the app.

1. **Install what is missing** (just warn that Windows will ask for administrator permission once):
   - No Python 3: *ask*, then install it (`winget install -e --id Python.Python.3.13`).
   - No `configurado.ok` in the root, or `detectar` says OpenRGB/driver are missing: run
     `powershell -NoProfile -ExecutionPolicy Bypass -File "1-Configurar (admin).ps1"` in the root. It waits until done
     and installs official OpenRGB, the libraries (`app/lib/pyXY`, reinstalled automatically if the Python version
     changes) and the PawnIO driver, and disables ASRock Polychrome at startup (reversible).
   - Start OpenRGB: `python rgb_controller.py conectar` (inside `app/`).
2. **Detect and save the PC profile without asking**: run `detectar`, then `configurar` (section 1) with:
   - friendly `nicknames` in the person's language, with the brand when it helps (e.g. "Motherboard",
     "Memory", "Logitech G PRO keyboard");
   - `links`: `{"DRAM": "mirror"}` when there are 2 or more RAM sticks;
   - `vendors` only to change the default (the Logitech G HUB bridge turns on by itself; peripherals without RGB need nothing);
   - `notes`: 1 to 3 sentences about what you found.
   - A vendor app fighting over the same hardware (e.g. Armoury Crate on an ASUS board): *ask* before disabling its
     startup (reversibly; never uninstall anything). Logitech G HUB is not a conflict.
3. **Ask only one thing: the style.** Offer 4 to 6 short options from `app/palettes.json` (e.g. GTA VI, Cyberpunk 2077,
   Synthwave, Aurora), plus "a game I like" and "my own colors".
4. **Apply with `ia`**: the chosen palette on every device, `"effect": "static"`, RAM sticks mirrored.
   Don't ask about effects, game mode or night mode: those live in the app.
5. If any device has `persist: "none"` (loses its color when the PC turns off), run `iniciar-com-windows sim`:
   it is part of the setup the person asked for.
6. **Open the app** (`Start-Process EasyRGB.bat` in the root) and reply in 3 or 4 lines: what you found, the look you
   applied, that effects (Computer and each peripheral), game mode and night mode are in the app, and that they can ask
   you for new looks anytime.

### What each device keeps by itself (`persist` in `detectar`)

- `auto`: the chip keeps its color when the PC turns off (e.g. ASRock boards).
- `manual`: keeps only one fixed color, with `save: true` / the "Save to board" button (e.g. some keyboards).
- `none`: loses its color when the PC turns off (e.g. ENE RAM). For these, turn on "restore colors on PC start".
- `vendor`: painted on top of the maker's app (e.g. G HUB); that app goes back to its own profile if EasyRGB closes.

"Restore on PC start" is light: at startup it brings the colors back and **closes everything by itself** (OpenRGB
included). It only stays in the background (~30 MB EasyRGB + ~60 MB OpenRGB) when there is game mode, schedules, an
animated effect or a vendor bridge. It runs through Windows' `pyw.exe`, so Python updates don't break it.

## 1. Configure the PC (first conversation, or when the user asks)

1. **Detect the hardware**: `python rgb_controller.py detectar`. Outputs JSON with motherboard, BIOS, CPU, RAM, GPU,
   USB peripherals, the devices OpenRGB sees (zones, LEDs and native effects of each), vendor RGB apps installed or
   running, `vendor_bridges` and `next_steps` with what is missing.
2. **Fix what is missing**, explaining in plain words:
   - `openrgb_installed` / `pawnio_driver` false: run the installer (section 0) or ask them to open `EasyRGB.bat`.
   - `openrgb_running` false: run `python rgb_controller.py conectar`.
   - `rgb_software_conflicts` with `running: true`: only a problem if that app controls the same devices as OpenRGB
     (e.g. Armoury Crate on an ASUS board). Explain and **ask before** disabling its startup. Disable it reversibly
     (scheduled task or service set to manual). Never uninstall anything.
   - A board or RAM with RGB that doesn't show in `openrgb_devices`: check https://openrgb.org/devices.html, whether
     OpenRGB runs as admin and whether RGB is disabled in the BIOS. Tell the user what you found.
3. **Save the PC profile** with what you found. The app shows "Set up by AI" and uses the nicknames:
   ```bash
   python rgb_controller.py configurar - <<'EOF'
   {"agent": "Agent name",
    "summary": "ASRock X570 Phantom Gaming 4, 2 ENE RGB RAM sticks, RGB keyboard",
    "motherboard": "ASRock X570 Phantom Gaming 4",
    "nicknames": {"0": "Motherboard", "3": "Keyboard"},
    "links": {"DRAM": "mirror"},
    "notes": ["The Logitech keyboard is painted through G HUB, no conflict."]}
   EOF
   ```
   - `nicknames`: device id (from `detectar`) -> friendly name.
   - `links`: default grouping per type (`DRAM`, `GPU`...): `separate`, `mirror` (same colors) or `span` (one continuous gradient).
   - `vendors` (optional): peripherals painted **on top of the maker's app**, without disabling it. See
     `vendor_bridges` in `detectar`: every PC is different, so only configure what exists on it.
     E.g. `"vendors": {"logitech": {"devices": [{"type": "mouse", "zones": 2, "name": "G502"}]}}`.
     `type`: `mouse`, `keyboard`, `headset`, `mousemat`, `speaker` or `all` (all of the brand's lights in one color,
     the default). `zones` = how many light areas the device has. `{"enabled": false}` turns the bridge off.
     For Logitech, ask them to turn on the G HUB option that lets games and apps control the lighting.
     Logitech keyboards that OpenRGB sees are painted key by key through G HUB automatically.
     Today there is a bridge for **Logitech G HUB**; for other brands use OpenRGB and mention the conflict.
4. **Apply a first look** (in quick setup, the palette the person picked).

## 2. Create looks: the user describes a mood and you apply it

Build a profile and apply it right away, without asking:

```bash
python rgb_controller.py ia - <<'EOF'
{"name": "Short name", "description": "One sentence about the look",
 "colors": ["#FF2E88", "#9B3DFF", "#00D9C8"],
 "mode": "gradiente",
 "brightness": 100,
 "effect": "static", "speed": 3,
 "peripheral_effects": {"teclado": "onda"},
 "zones": [{"device": "teclado", "color": "#FFFFFF"},
           {"device": "placa", "zone": "IO Cover", "color": "#FF0000"}],
 "hw": [{"device": "ram", "mode": "Chase", "speed": 60}],
 "links": {"ram": "span"},
 "exclude": [],
 "save": false}
EOF
```

In PowerShell, save the JSON to a file and run `python rgb_controller.py ia look.json`.

- `mode`: `gradiente` (gradient), `alternado` (alternating) or `zona` (one palette color per zone).
- `effect`: app-driven animated effect for the computer: `static`, `fluir` (flow), `respirar` (breathe),
  `ciclo` (color cycle), `arcoiris` (rainbow), `musica` (reacts to PC audio), `onda` (color wave with the palette;
  `"direction"`: `direita`, `esquerda`, `baixo`, `cima`, `centro` or `dentro`), `estrelas` (starlight),
  `tela` (copies screen colors) or `teclas` (each key press sends out a ring of color).
  On keyboards these follow the real key positions. `speed` goes from 1 to 10. Runs only while EasyRGB is open.
- `peripheral_effects` (optional): a peripheral's own effect, separate from the computer. E.g.
  `"effect": "static", "peripheral_effects": {"teclado": "onda"}` keeps board and RAM still and only the keyboard waves.
  `estrelas`, `tela` and `teclas` are made for keyboards; use them here rather than in the computer's `effect`.
- `hw`: the **chip's native effect** on a device (exact names come from `detectar` or `listar`, e.g. `Breathing`,
  `Chase`, `Rainbow`). `speed` from 0 to 100. Runs by itself, even with the app closed. Effects with `colors: "led"`
  or `"mode"` use the palette; `"none"` use the chip's own colors. Not offered for devices painted through G HUB.
- `device` accepts `placa` (motherboard), `ram`, `teclado` (keyboard), `mouse`, `gpu`, the id (`0`..) or part of the name.
  `zone` is optional.
- `links`: groups devices of the same type: `separate`, `mirror` or `span`.
- `exclude`: devices left out.
- `save: true` writes to the board/RAM memory (survives reboots). Only when the user wants to lock it in.
- The look shows in the app's AI area with history, and the page updates by itself.
- Prefer vivid, saturated colors: grays and dark tones look bad on LEDs.
- Ready-made presets (games and classics) are in `app/palettes.json`; use them as a starting point.

## 3. Automation: games, schedules and start with Windows

When the user asks for something like "when I open Valorant, make it red" or "dim the lights at night":

1. `python rgb_controller.py jogos` lists known installed games (Steam, Epic, Riot, Xbox) and the suggested preset.
2. `python rgb_controller.py automacao` shows the current rules. To save, **read the current ones and send the full list**
   (the command replaces everything):
   ```bash
   python rgb_controller.py automacao - <<'EOF'
   {"enabled": true,
    "games": [{"process": "VALORANT-Win64-Shipping.exe", "preset": "Valorant"},
              {"process": "cs2.exe", "preset": "Counter-Strike 2"}],
    "schedule": [{"time": "23:00", "action": "brightness", "value": 20},
                 {"time": "08:00", "action": "restore"},
                 {"time": "19:00", "action": "preset", "value": "Synthwave"}]}
   EOF
   ```
   - `games`: while the executable is open, its preset is used; when it closes, the user's look comes back.
     The preset must exist in `app/palettes.json` or the user's presets (create it first if new).
   - `schedule[].action`: `preset` (value = name), `brightness` (value = %), `off` or `restore` (saved look).
   - Works while EasyRGB is open (or started with Windows).
3. `python rgb_controller.py iniciar-com-windows sim` creates a logon task that restores colors after a reboot and
   closes by itself when nothing needs to keep running (asks for admin once). Outside quick setup, **ask first**: it is
   a system change. `nao` removes it.

## Presets, keyboard, shortcuts and tray

- Built-in presets live in `app/palettes.json` (don't edit). The user's own live in `app/my_presets.json`
  (create them in the app or by writing `{"Name": ["#RRGGBB", ...]}` to that file).
- Keyboard: per-key colors with `"L<index>"` keys in `overrides` (indexes and names in `led_names` from `detectar`).
- `automacao` accepts `"hotkeys": true` (Ctrl+Alt + arrows/E/L shortcuts). EasyRGB runs without a window, with a tray
  icon; errors go to `app/easyrgb.log`.

## Other commands

- `python rgb_controller.py listar`: devices, zones and chip effects.
- `python rgb_controller.py aplicar <preset or colors> [--brilho 80] [--modo zona] [--gravar]`
- `python rgb_controller.py compartilhar` / `importar EASYRGB1-...`: share codes to swap looks between people.
- `python rgb_controller.py bibliotecas`: installs the libraries for the current Python.
- `python rgb_controller.py desligar`: lights off.

## Tests

- `python -m unittest discover -s tests -v`: color logic, simulated hardware, automation, API, UI and Python x
  JavaScript parity (that one needs Node.js). Run after any change.
- `EASYRGB_HW=1 python -m unittest tests.test_hardware -v`: test on the real hardware (lights blink and come back).

## Notes for agents

- If the agent runs in a sandbox, commands need access to the local network (ports 6742 and 6750) and the real files.
- `detectar` takes a few seconds (it queries Windows through PowerShell).

## Code conventions

- UI uses SVG icons (Lucide style), never emojis. Sober look: dark zinc background, white primary button.
- Every UI string has an English translation in the `EN` table of `index.html` (tests check it).
- The color logic exists in two places and must match: `plan_colors` in Python and `plan()` in `index.html`.
- `.gitignore` leaves out each PC's state (`last_state.json`, `claude_color.json`, `pc.json`, `automations.json`,
  `my_presets.json`, logs and `app/lib/`).
