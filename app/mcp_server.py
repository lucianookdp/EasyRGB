"""EasyRGB MCP server: lets AI chat apps (Claude Desktop, Claude Code, Cursor, VS Code...) control the PC's RGB.

Speaks the Model Context Protocol over stdio (JSON-RPC 2.0, one message per line) using only the standard library.
It talks to the local EasyRGB app (http://127.0.0.1:6750) and starts it if it isn't running.

Run:  python app/mcp_server.py      or      EasyRGB.exe --mcp
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:6750"
PROTOCOL = "2025-06-18"
FROZEN = bool(getattr(sys, "frozen", False))
SRC = Path(__file__).resolve().parent

INSTRUCTIONS = (
    "EasyRGB controls this PC's RGB lighting (motherboard, RAM, LED strips, keyboard and other peripherals). "
    "When the user describes a look or mood, call easyrgb_apply_look with vivid, saturated colors (2 to 5 hex colors). "
    "Call easyrgb_status first if you need the device list, the current look or preset names. "
    "Answer the user in their own language."
)

EFFECTS = ["static", "onda", "respirar", "ciclo", "arcoiris", "fluir", "musica", "estrelas", "tela", "teclas"]
EFFECT_HELP = ("static=no animation, onda=color wave, respirar=breathe, ciclo=color cycle, arcoiris=rainbow, "
               "fluir=flow, musica=reacts to music, estrelas=starlight (keyboard), tela=screen colors (keyboard), "
               "teclas=key-press ripple (keyboard)")

TOOLS = [
    {"name": "easyrgb_status",
     "description": "Current RGB look (palette, effects, brightness), the PC's RGB devices and the available presets.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "easyrgb_apply_look",
     "description": "Apply a lighting look to the PC. Give either `colors` or `preset`; anything left out keeps its "
                    "current value. Saved as the user's look and shown in the EasyRGB app history. "
                    "Animated effects run while EasyRGB is open. Effects: " + EFFECT_HELP + ".",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "Short name for the look, e.g. 'Cyberpunk night'"},
         "colors": {"type": "array", "items": {"type": "string"}, "description": "2-5 hex colors like #FF2E88"},
         "preset": {"type": "string", "description": "Name of a preset from easyrgb_status (e.g. 'GTA VI')"},
         "brightness": {"type": "integer", "minimum": 5, "maximum": 100},
         "mode": {"type": "string", "enum": ["gradiente", "alternado", "zona"],
                  "description": "gradiente=smooth gradient, alternado=alternating LEDs, zona=one color per zone"},
         "effect": {"type": "string", "enum": EFFECTS, "description": "Effect for the computer (board, RAM, strips)"},
         "peripheral_effects": {"type": "object", "additionalProperties": {"type": "string", "enum": EFFECTS},
                                "description": "Per-peripheral effect, e.g. {\"teclado\": \"onda\"} (keyboard wave)"},
         "speed": {"type": "integer", "minimum": 1, "maximum": 10},
         "direction": {"type": "string", "enum": ["direita", "esquerda", "baixo", "cima", "centro", "dentro"],
                       "description": "Color wave direction: right, left, down, up, center-out, outside-in"}}}},
    {"name": "easyrgb_brightness",
     "description": "Change the brightness of all lights (5-100%) without changing the colors.",
     "inputSchema": {"type": "object", "properties": {"percent": {"type": "integer", "minimum": 5, "maximum": 100}},
                     "required": ["percent"]}},
    {"name": "easyrgb_lights",
     "description": "Turn all RGB lights off, or back on with the saved look.",
     "inputSchema": {"type": "object", "properties": {"on": {"type": "boolean"}}, "required": ["on"]}},
]


# ---------------------------------------------------------------- EasyRGB app
def _call(path, body=None, timeout=60):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except Exception:
            msg = None
        raise RuntimeError(msg or f"EasyRGB error {e.code}")


def _running():
    try:
        _call("/api/claude", timeout=3)
        return True
    except Exception:
        return False


def ensure_app():
    """Start the EasyRGB app in the background if it is closed (tray icon, no window)."""
    if _running():
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    if FROZEN:
        cmd = [sys.executable, "--no-browser"]
    else:
        pyw = Path(sys.executable).with_name("pythonw.exe")
        cmd = [str(pyw if pyw.exists() else sys.executable), str(SRC / "rgb_controller.py"), "--no-browser"]
    subprocess.Popen(cmd, cwd=str(SRC if not FROZEN else Path(sys.executable).parent), creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        time.sleep(1)
        if _running():
            return
    raise RuntimeError("EasyRGB didn't start. Open EasyRGB once to finish its setup.")


# ---------------------------------------------------------------- tools
def tool_status(_args):
    st = _call("/api/state")
    last = st.get("last") or {}
    ui = last.get("ui") or {}
    devs = [{"id": d["id"], "name": (st.get("pc") or {}).get("nicknames", {}).get(str(d["id"])) or d["name"],
             "type": d["type"], "leds": sum(z["leds"] for z in d["zones"])} for d in st.get("devices", [])]
    return {"connected": st.get("connected"), "devices": devs,
            "look": {"colors": last.get("palette"), "brightness": last.get("brightness"), "mode": last.get("mode"),
                     "effect": ui.get("effect", "static"), "peripheral_effects": ui.get("pfx") or {}},
            "presets": list((st.get("palettes") or {}).keys()),
            "conflicts": st.get("conflicts") or []}


def tool_apply(args):
    st = _call("/api/state")
    last = st.get("last") or {}
    ui = last.get("ui") or {}
    colors = args.get("colors")
    if not colors and args.get("preset"):
        want = args["preset"].strip().lower()
        pal = st.get("palettes") or {}
        name = next((n for n in pal if n.lower() == want), None) or next((n for n in pal if want in n.lower()), None)
        if not name:
            raise RuntimeError(f"Preset not found: {args['preset']}. Available: {', '.join(pal)}")
        colors = pal[name]
        args.setdefault("name", name)
    colors = colors or last.get("palette")
    if not colors:
        raise RuntimeError("Give `colors` or `preset`.")
    pfx_names = {}
    if "peripheral_effects" not in args and ui.get("pfx"):   # keep per-device effects the user set
        devs = {str(d["id"]): d["name"] for d in st.get("devices", [])}
        pfx_names = {devs[k]: v for k, v in ui["pfx"].items() if k in devs}
    profile = {"name": args.get("name") or "AI look", "colors": colors,
               "brightness": int(args.get("brightness", last.get("brightness", 100))),
               "mode": args.get("mode", last.get("mode", "gradiente")),
               "effect": args.get("effect", ui.get("effect", "static")),
               "speed": int(args.get("speed", ui.get("speed", 3))),
               "direction": args.get("direction", ui.get("dir", "direita")),
               "peripheral_effects": args.get("peripheral_effects", pfx_names),
               "links": ui.get("links") or {}}
    res = _call("/api/claude", profile)
    bad = [r["device"] for r in res.get("report", []) if not r.get("ok")]
    return {"applied": profile["name"], "colors": colors, "effect": profile["effect"],
            "peripheral_effects": profile["peripheral_effects"], "failed_devices": bad}


def tool_brightness(args):
    _call("/api/quick", {"action": "brightness", "value": int(args["percent"])})
    return {"brightness": int(args["percent"])}


def tool_lights(args):
    if args.get("on"):
        L = (_call("/api/state").get("last") or {})
        if not L.get("palette"):
            raise RuntimeError("No saved look yet: apply one first.")
        ui = L.get("ui") or {}
        _call("/api/effect", {"on": True, "persist": True, "colors": L["palette"], "brightness": L.get("brightness", 100),
                              "mode": L.get("mode", "gradiente"), "devices": L.get("devices"),
                              "overrides": L.get("overrides", {}), "groups": L.get("groups", []), "hw": L.get("hw", {}),
                              "kind": ui.get("effect", "static"), "speed": ui.get("speed", 3), "ui": ui})
        return {"lights": "on"}
    _call("/api/off", {})
    return {"lights": "off"}


HANDLERS = {"easyrgb_status": tool_status, "easyrgb_apply_look": tool_apply,
            "easyrgb_brightness": tool_brightness, "easyrgb_lights": tool_lights}


# ---------------------------------------------------------------- MCP (JSON-RPC over stdio)
def handle(msg):
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
    if not isinstance(msg.get("params"), (dict, type(None))):
        msg = dict(msg, params={})
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:   # notification (e.g. notifications/initialized): no reply
        return None
    if method == "initialize":
        ver = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": ver, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "easyrgb", "title": "EasyRGB", "version": "1.2.3"},
            "instructions": INSTRUCTIONS}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        p = msg.get("params") or {}
        fn = HANDLERS.get(p.get("name"))
        if not fn:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool {p.get('name')}"}}
        try:
            ensure_app()
            out = fn(dict(p.get("arguments") or {}))
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}], "isError": False}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": f"EasyRGB: {e}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def serve(inp=None, out=None):
    inp = inp or sys.stdin
    out = out or sys.stdout
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = handle(msg)
        if reply is not None:
            out.write(json.dumps(reply, ensure_ascii=False) + "\n")
            out.flush()


# ---------------------------------------------------------------- install into AI apps
def claude_desktop_configs():
    """Where Claude Desktop reads its config: %APPDATA%/Claude (regular installer) and, for the Microsoft Store
    version, the package folder under %LOCALAPPDATA%/Packages/Claude_*."""
    import os
    paths = [Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"]
    pkgs = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
    if pkgs.exists():
        for d in pkgs.glob("Claude_*"):
            paths.append(d / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json")
    return paths


def server_command():
    """Command an AI app runs to start this server."""
    if FROZEN:
        return {"command": sys.executable, "args": ["--mcp"]}
    import os
    launcher = Path(os.environ.get("WINDIR", r"C:\Windows")) / "py.exe"   # acha o Python instalado na hora
    if launcher.exists():
        return {"command": str(launcher), "args": [str(SRC / "mcp_server.py")]}
    exe = Path(sys.executable)
    py = exe.with_name("python.exe") if exe.name.lower() == "pythonw.exe" else exe
    return {"command": str(py), "args": [str(SRC / "mcp_server.py")]}


# ---------------------------------------------------------------- the most used AI apps, one click each
def _home():
    import os
    return Path(os.environ.get("USERPROFILE") or Path.home())


def _env(name):
    import os
    return Path(os.environ.get(name, ""))


def _json_files(paths, key="mcpServers", extra=None):
    """Config files in the common JSON shape {key: {name: {command, args}}}."""
    return {"kind": "json", "files": paths, "section": key, "extra": extra or {}}


def ai_clients():
    """Popular AI apps that run local MCP servers, with where each one keeps its config (Windows)."""
    home, appdata, local = _home(), _env("APPDATA"), _env("LOCALAPPDATA")
    pkgs = local / "Packages"
    claude_pkgs = list(pkgs.glob("Claude_*")) if pkgs.exists() else []
    return [
        {"key": "claude-desktop", "name": "Claude Desktop", "hint": "Restart Claude Desktop.",
         "detect": [appdata / "Claude", *claude_pkgs], **_json_files(claude_desktop_configs())},
        {"key": "claude-code", "name": "Claude Code", "hint": "Start a new Claude Code session.",
         "detect": [home / ".claude.json"], **_json_files([home / ".claude.json"], extra={"type": "stdio"})},
        {"key": "cursor", "name": "Cursor", "hint": "In Cursor: Settings, MCP, turn EasyRGB on.",
         "detect": [home / ".cursor", local / "Programs" / "cursor"], **_json_files([home / ".cursor" / "mcp.json"])},
        {"key": "copilot", "name": "GitHub Copilot (VS Code)",
         "hint": "In VS Code: open Copilot Chat in Agent mode; EasyRGB shows in the tools list.",
         "detect": [appdata / "Code" / "User"],
         **_json_files([appdata / "Code" / "User" / "mcp.json"], key="servers", extra={"type": "stdio"})},
        {"key": "windsurf", "name": "Windsurf", "hint": "In Windsurf: Cascade, MCP servers, Refresh.",
         "detect": [home / ".codeium" / "windsurf", local / "Programs" / "Windsurf"],
         **_json_files([home / ".codeium" / "windsurf" / "mcp_config.json"])},
        {"key": "gemini", "name": "Gemini CLI", "hint": "Start a new Gemini CLI session.",
         "detect": [home / ".gemini"], **_json_files([home / ".gemini" / "settings.json"])},
        {"key": "codex", "name": "Codex (OpenAI)", "hint": "Start a new Codex session.",
         "detect": [home / ".codex"], "kind": "toml", "files": [home / ".codex" / "config.toml"]},
        {"key": "lmstudio", "name": "LM Studio", "hint": "In LM Studio: Program, Install, reload MCP.",
         "detect": [home / ".lmstudio"], **_json_files([home / ".lmstudio" / "mcp.json"])},
    ]


def _toml_str(s):
    return "'" + s + "'" if "'" not in s else json.dumps(s)   # literal string: backslashes stay as they are


def _toml_block(cmd):
    return (f"[mcp_servers.easyrgb]\ncommand = {_toml_str(cmd['command'])}\n"
            f"args = [{', '.join(_toml_str(a) for a in cmd['args'])}]\n")


def _toml_has(text):
    return "[mcp_servers.easyrgb]" in text


def _toml_without(text):
    """Removes the [mcp_servers.easyrgb] table (up to the next table or the end)."""
    import re
    out = re.sub(r"(?ms)^\[mcp_servers\.easyrgb\]\r?\n.*?(?=^\[|\Z)", "", text).rstrip()
    return out + "\n" if out else ""


def client_connected(c):
    for f in c["files"]:
        if not f.exists():
            continue
        try:
            text = f.read_text(encoding="utf-8")
            if c["kind"] == "toml" and _toml_has(text):
                return True
            if c["kind"] == "json" and "easyrgb" in (json.loads(text or "{}").get(c["section"]) or {}):
                return True
        except (OSError, ValueError):
            pass
    return False


def list_clients():
    return [{"key": c["key"], "name": c["name"], "hint": c["hint"],
             "found": any(p.exists() for p in c["detect"]), "connected": client_connected(c)} for c in ai_clients()]


def connect_client(key):
    """Adds EasyRGB to that AI app's MCP servers, keeping everything else in the file. Returns the files written."""
    c = next((c for c in ai_clients() if c["key"] == key), None)
    if not c:
        raise ValueError(f"Unknown AI app: {key}")
    cmd, done = server_command(), []
    for f in c["files"]:
        text = f.read_text(encoding="utf-8") if f.exists() else ""
        if c["kind"] == "toml":
            rest = _toml_without(text) if _toml_has(text) else text
            new = (rest.rstrip() + "\n\n" + _toml_block(cmd)) if rest.strip() else _toml_block(cmd)
        else:
            try:
                data = json.loads(text or "{}")
            except ValueError:
                continue   # arquivo com erro de digitação: não sobrescreve o que a pessoa escreveu
            data.setdefault(c["section"], {})["easyrgb"] = {**c["extra"], **cmd}
            new = json.dumps(data, indent=2, ensure_ascii=False)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(new, encoding="utf-8")
        done.append(f)
    if not done:
        raise ValueError("The AI app's config file has an error; fix it or use Other AI.")
    return done


def disconnect_all():
    """Takes EasyRGB out of every AI app (used by 'Undo everything')."""
    out = []
    for c in ai_clients():
        for f in c["files"]:
            if not f.exists():
                continue
            try:
                text = f.read_text(encoding="utf-8")
                if c["kind"] == "toml":
                    if _toml_has(text):
                        f.write_text(_toml_without(text), encoding="utf-8")
                        out.append(c["key"])
                    continue
                data = json.loads(text or "{}")
                if (data.get(c["section"]) or {}).pop("easyrgb", None) is not None:
                    f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                    out.append(c["key"])
            except (OSError, ValueError):
                pass
    return out


def manual_config():
    """For any other AI app: the same server, to copy."""
    cmd = server_command()
    return {"json": json.dumps({"mcpServers": {"easyrgb": cmd}}, indent=2), **cmd}


def install_claude_desktop():
    return connect_client("claude-desktop")


if __name__ == "__main__":
    if "--install-claude-desktop" in sys.argv:
        print("OK:", ", ".join(map(str, install_claude_desktop())), "- restart Claude Desktop.")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        serve()
