"""
Lawrence: Move In — CornerLaunch v1.0.0
Hot-corner overlay — mouse to top-right → grid of categorised commands.
Ported from Electron RightCorner to pure Python + Chromium app-mode.
Categories: AI chatbots, scripts, browser, system, windows, power.
"""
__version__ = "1.0.0"
import selfclean; selfclean.ensure_single("corner_launch.py")

import ctypes, json, os, shutil, subprocess, sys, threading, time, webbrowser
import tempfile, winreg
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from PIL import Image as PILImage, ImageDraw
import pystray
import win32api, win32gui

SCRIPT_DIR = Path(__file__).resolve().parent
COMMANDS_FILE = SCRIPT_DIR / "corner_commands.json"

# ── Colour palette (matches suite) ────────────────────────────────────────────
BG     = "#0d1117"
BG2    = "#161b22"
BG3    = "#21262d"
BG4    = "#30363d"
FG     = "#e6edf3"
DIM    = "#6e7681"
BLUE   = "#79c0ff"
GREEN  = "#7ee787"
YELLOW = "#e3b341"
RED    = "#ff7b72"
TEAL   = "#76e3ea"
PURPLE = "#d2a8ff"

# ── Default commands ──────────────────────────────────────────────────────────
DEFAULT_COMMANDS = {
    "categories": [
        {"id": "all",       "label": "All",          "color": "#6366f1", "icon": "🏠"},
        {"id": "ai",        "label": "AI Chatbots",  "color": "#06b6d4", "icon": "🧠"},
        {"id": "browser",   "label": "Browser",      "color": "#f97316", "icon": "🌐"},
        {"id": "scripts",   "label": "Scripts",      "color": "#14b8a6", "icon": "⚡"},
        {"id": "window",    "label": "Windows",      "color": "#3b82f6", "icon": "🪟"},
        {"id": "suite",     "label": "Arms & Legs",  "color": TEAL,     "icon": "🦾"},
        {"id": "system",    "label": "System",       "color": "#8b5cf6", "icon": "⚙️"},
        {"id": "power",     "label": "Power",        "color": "#ef4444", "icon": "🔌"},
    ],
    "commands": [
        # ── AI ──
        {"id": "claude",      "label": "Claude",       "category": "ai", "icon": "🧊", "action": {"type": "url", "url": "https://claude.ai/new"}},
        {"id": "chatgpt",     "label": "ChatGPT",      "category": "ai", "icon": "🧠", "action": {"type": "url", "url": "https://chat.openai.com/"}},
        {"id": "gemini",      "label": "Gemini",       "category": "ai", "icon": "✨", "action": {"type": "url", "url": "https://gemini.google.com/"}},
        {"id": "perplexity",  "label": "Perplexity",   "category": "ai", "icon": "🔍", "action": {"type": "url", "url": "https://www.perplexity.ai/"}},
        {"id": "copilot",     "label": "Copilot",      "category": "ai", "icon": "🚀", "action": {"type": "url", "url": "https://copilot.microsoft.com/"}},
        {"id": "grok",        "label": "Grok",         "category": "ai", "icon": "🌟", "action": {"type": "url", "url": "https://grok.x.ai/"}},
        # ── Browser ──
        {"id": "new-tab",     "label": "New Tab",      "category": "browser", "icon": "➕", "action": {"type": "url", "url": "about:blank"}},
        {"id": "github",      "label": "GitHub",       "category": "browser", "icon": "🐙", "action": {"type": "url", "url": "https://github.com/lozturner"}},
        {"id": "youtube",     "label": "YouTube",      "category": "browser", "icon": "▶️",  "action": {"type": "url", "url": "https://youtube.com"}},
        {"id": "notion",      "label": "Notion",       "category": "browser", "icon": "📝", "action": {"type": "url", "url": "https://notion.so"}},
        # ── Scripts ──
        {"id": "powershell",  "label": "PowerShell",   "category": "scripts", "icon": "💻", "action": {"type": "run", "cmd": "powershell.exe"}},
        {"id": "cmd",         "label": "CMD",          "category": "scripts", "icon": "📺", "action": {"type": "run", "cmd": "cmd.exe"}},
        {"id": "claude-code", "label": "Claude Code",  "category": "scripts", "icon": "🤖", "action": {"type": "run", "cmd": "cmd.exe", "args": "/k claude"}},
        # ── Windows ──
        {"id": "task-view",   "label": "Task View",    "category": "window", "icon": "📊", "action": {"type": "hotkey", "keys": "win+tab"}},
        {"id": "desktop",     "label": "Desktop",      "category": "window", "icon": "🖥️",  "action": {"type": "hotkey", "keys": "win+d"}},
        {"id": "snap-left",   "label": "Snap Left",    "category": "window", "icon": "◀️",  "action": {"type": "hotkey", "keys": "win+left"}},
        {"id": "snap-right",  "label": "Snap Right",   "category": "window", "icon": "▶️",  "action": {"type": "hotkey", "keys": "win+right"}},
        {"id": "close-win",   "label": "Close Window", "category": "window", "icon": "❌", "action": {"type": "hotkey", "keys": "alt+f4"}},
        # ── Arms & Legs suite ──
        {"id": "s-mermaid",   "label": "MermaidBot",   "category": "suite", "icon": "🧩", "action": {"type": "suite", "script": "mermaidbot.py"}},
        {"id": "s-floatbar",  "label": "FloatBar",     "category": "suite", "icon": "🌊", "action": {"type": "suite", "script": "floatbar.py"}},
        {"id": "s-niggly",    "label": "Niggly",       "category": "suite", "icon": "📌", "action": {"type": "suite", "script": "niggly.py"}},
        {"id": "s-tiles",     "label": "Tiles",        "category": "suite", "icon": "🏁", "action": {"type": "suite", "script": "tiles.py"}},
        {"id": "s-branch",    "label": "WinBranch",    "category": "suite", "icon": "🌳", "action": {"type": "suite", "script": "windowbranch.py"}},
        {"id": "s-hotcorner", "label": "Hot Corners",  "category": "suite", "icon": "🔥", "action": {"type": "suite", "script": "hot_corner.py"}},
        {"id": "s-windowbot", "label": "WindowBot",    "category": "suite", "icon": "🤖", "action": {"type": "suite", "script": "windowbot.py"}},
        {"id": "s-launcher",  "label": "Launcher",     "category": "suite", "icon": "🚀", "action": {"type": "suite", "script": "launcher.py"}},
        # ── System ──
        {"id": "settings",    "label": "Settings",     "category": "system", "icon": "⚙️", "action": {"type": "run", "cmd": "ms-settings:"}},
        {"id": "taskmanager", "label": "Task Manager", "category": "system", "icon": "📋", "action": {"type": "run", "cmd": "taskmgr.exe"}},
        {"id": "explorer",    "label": "Explorer",     "category": "system", "icon": "📁", "action": {"type": "run", "cmd": "explorer.exe"}},
        # ── Power ──
        {"id": "lock",        "label": "Lock",         "category": "power", "icon": "🔒", "action": {"type": "hotkey", "keys": "win+l"}},
        {"id": "sleep",       "label": "Sleep",        "category": "power", "icon": "😴", "action": {"type": "run", "cmd": "rundll32.exe", "args": "powrprof.dll,SetSuspendState 0,1,0"}},
        {"id": "restart",     "label": "Restart",      "category": "power", "icon": "🔄", "action": {"type": "run", "cmd": "shutdown", "args": "/r /t 5"}},
    ],
}


def _load_commands() -> dict:
    if COMMANDS_FILE.exists():
        try:
            return json.loads(COMMANDS_FILE.read_text("utf-8"))
        except Exception:
            pass
    # Write defaults on first run
    COMMANDS_FILE.write_text(json.dumps(DEFAULT_COMMANDS, indent=2, ensure_ascii=False), "utf-8")
    return DEFAULT_COMMANDS


# ── Chromium finder (shared pattern) ──────────────────────────────────────────
def _find_chromium() -> str:
    local = os.environ.get("LOCALAPPDATA", "")
    for p in [
        os.path.join(local, "Perplexity", "Comet", "Application", "comet.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.join(local, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ]:
        if os.path.isfile(p):
            return p
    return ""


# ── Key simulation ────────────────────────────────────────────────────────────
VK_MAP = {
    'win': 0x5B, 'tab': 0x09, 'left': 0x25, 'right': 0x27,
    'up': 0x26, 'down': 0x28, 'd': 0x44, 'l': 0x4C,
    'alt': 0x12, 'f4': 0x73, 'ctrl': 0x11, 'shift': 0x10,
}

def _press_hotkey(keys_str: str):
    """Simulate a hotkey combo like 'win+tab' or 'alt+f4'."""
    import ctypes
    user32 = ctypes.windll.user32
    parts = [k.strip().lower() for k in keys_str.split('+')]
    vks = [VK_MAP.get(p, ord(p.upper()) if len(p) == 1 else 0) for p in parts]
    for vk in vks:
        if vk: user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    for vk in reversed(vks):
        if vk: user32.keybd_event(vk, 0, 0x0002, 0)  # KEYEVENTF_KEYUP


# ── Command executor ──────────────────────────────────────────────────────────
PYTHONW = str(Path(sys.executable).with_name("pythonw.exe"))

def _execute_command(cmd_data: dict) -> dict:
    action = cmd_data.get("action", {})
    atype = action.get("type", "")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    try:
        if atype == "url":
            webbrowser.open(action["url"])
            return {"ok": True}

        elif atype == "run":
            cmd = action["cmd"]
            args_str = action.get("args", "")
            if cmd.startswith("ms-"):
                os.startfile(cmd)
            elif args_str:
                subprocess.Popen(f'{cmd} {args_str}', creationflags=flags, shell=True)
            else:
                subprocess.Popen([cmd], creationflags=flags)
            return {"ok": True}

        elif atype == "hotkey":
            _press_hotkey(action["keys"])
            return {"ok": True}

        elif atype == "suite":
            script = action["script"]
            script_path = SCRIPT_DIR / script
            if script_path.exists():
                import selfclean as sc
                sc.safe_launch(script)
            return {"ok": True}

        else:
            return {"ok": False, "error": f"Unknown action type: {atype}"}

    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ── Overlay HTML ──────────────────────────────────────────────────────────────
def _make_overlay_html(commands_data: dict) -> str:
    cats_json = json.dumps(commands_data["categories"], ensure_ascii=False)
    cmds_json = json.dumps(commands_data["commands"], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CornerLaunch v{__version__}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:{BG};--bg2:{BG2};--bg3:{BG3};--bg4:{BG4};
  --fg:{FG};--dim:{DIM};--blue:{BLUE};--green:{GREEN};
  --teal:{TEAL};--red:{RED};--purple:{PURPLE};--yellow:{YELLOW};
}}
html,body{{
  height:100%;overflow:hidden;
  background:rgba(13,17,23,.92);
  backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);
  color:var(--fg);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px;
}}
/* ── Header ── */
#header{{
  -webkit-app-region:drag;
  display:flex;align-items:center;gap:8px;
  padding:10px 16px 6px;user-select:none;
}}
#header *{{-webkit-app-region:no-drag}}
.brand{{color:var(--teal);font-weight:800;font-size:15px;letter-spacing:.03em}}
.ver{{color:var(--dim);font-size:10px;margin-left:2px}}
#search{{
  flex:1;background:var(--bg3);color:var(--fg);
  border:1px solid var(--bg4);border-radius:8px;
  padding:6px 12px;font-size:13px;outline:none;
  margin-left:12px;
}}
#search:focus{{border-color:var(--blue)}}
#search::placeholder{{color:var(--dim)}}
.close-btn{{
  background:none;border:none;color:var(--dim);
  font-size:18px;cursor:pointer;padding:4px 8px;
  border-radius:6px;
}}
.close-btn:hover{{color:var(--red);background:rgba(255,123,114,.1)}}

/* ── Pills ── */
#pills{{
  display:flex;gap:4px;padding:8px 16px 4px;
  overflow-x:auto;flex-wrap:nowrap;
}}
.pill{{
  background:var(--bg3);color:var(--dim);
  border:1px solid transparent;border-radius:20px;
  padding:4px 12px;font-size:11px;font-weight:600;
  cursor:pointer;white-space:nowrap;
  transition:all .15s;
}}
.pill:hover{{color:var(--fg);border-color:var(--bg4)}}
.pill.active{{color:var(--fg);border-color:var(--blue);background:rgba(121,192,255,.08)}}

/* ── Grid ── */
#grid{{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(100px,1fr));
  gap:8px;padding:10px 16px;
  overflow-y:auto;
  max-height:calc(100vh - 110px);
}}
.tile{{
  background:var(--bg2);border:1px solid var(--bg4);
  border-radius:10px;padding:14px 8px 10px;
  text-align:center;cursor:pointer;
  transition:all .15s;position:relative;
  border-top:2px solid transparent;
}}
.tile:hover{{
  background:var(--bg3);
  transform:translateY(-2px);
  box-shadow:0 4px 16px rgba(0,0,0,.4);
}}
.tile-icon{{font-size:24px;display:block;margin-bottom:6px}}
.tile-label{{font-size:11px;color:var(--fg);font-weight:600;line-height:1.3}}

/* ── Status ── */
#status{{
  position:fixed;bottom:0;left:0;right:0;
  padding:4px 16px;font-size:10px;color:var(--dim);
  background:var(--bg2);border-top:1px solid var(--bg3);
  display:flex;align-items:center;gap:12px;
}}
#status .ver{{margin-left:auto}}

/* ── Anim ── */
.tile{{animation:fadeUp .2s ease both}}
@keyframes fadeUp{{
  from{{opacity:0;transform:translateY(8px)}}
  to{{opacity:1;transform:translateY(0)}}
}}
.tile:nth-child(2){{animation-delay:.02s}}
.tile:nth-child(3){{animation-delay:.04s}}
.tile:nth-child(4){{animation-delay:.06s}}
.tile:nth-child(5){{animation-delay:.08s}}
.tile:nth-child(6){{animation-delay:.10s}}
.tile:nth-child(7){{animation-delay:.12s}}
.tile:nth-child(8){{animation-delay:.14s}}
</style>
</head>
<body>

<div id="header">
  <span class="brand">🦾 CornerLaunch</span>
  <span class="ver">v{__version__}</span>
  <input id="search" type="text" placeholder="Search commands…" autofocus />
  <button class="close-btn" onclick="window.close()" title="Close">×</button>
</div>

<div id="pills"></div>
<div id="grid"></div>

<div id="status">
  <span id="count">—</span>
  <span>Esc = close · Click = run</span>
  <span class="ver">Arms & Legs Suite</span>
</div>

<script>
const CATS = {cats_json};
const CMDS = {cmds_json};
let activeCat = 'all';
let query = '';

function render(){{
  // Pills
  const pills = document.getElementById('pills');
  pills.innerHTML = CATS.map(c=>
    `<button class="pill ${{c.id===activeCat?'active':''}}"
      style="${{c.id===activeCat?'border-color:'+c.color+';color:'+c.color:''}}"
      onclick="setCat('${{c.id}}')">${{c.icon||''}} ${{c.label}}</button>`
  ).join('');

  // Filter
  let filtered = CMDS;
  if(activeCat!=='all') filtered=filtered.filter(c=>c.category===activeCat);
  if(query) filtered=filtered.filter(c=>
    c.label.toLowerCase().includes(query)||
    (c.category||'').toLowerCase().includes(query)
  );

  // Grid
  const grid = document.getElementById('grid');
  grid.innerHTML = filtered.map((c,i)=>{{
    const cat = CATS.find(x=>x.id===c.category);
    const borderCol = cat?cat.color:'var(--bg4)';
    return `<div class="tile" style="border-top-color:${{borderCol}};animation-delay:${{i*.02}}s"
      onclick="exec('${{c.id}}')">
      <span class="tile-icon">${{c.icon||'⬜'}}</span>
      <span class="tile-label">${{c.label}}</span>
    </div>`;
  }}).join('');

  document.getElementById('count').textContent = filtered.length+' commands';
}}

function setCat(id){{ activeCat=id; render(); }}

document.getElementById('search').addEventListener('input',e=>{{
  query=e.target.value.toLowerCase().trim();
  render();
}});

async function exec(cmdId){{
  const cmd = CMDS.find(c=>c.id===cmdId);
  if(!cmd) return;
  try{{
    const resp = await fetch('/api',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify(cmd)
    }});
    const data = await resp.json();
    if(data.ok){{
      // Brief green flash then close
      document.body.style.background='rgba(126,231,135,.06)';
      setTimeout(()=>window.close(),300);
    }} else {{
      document.getElementById('count').textContent='Error: '+(data.error||'');
    }}
  }}catch(e){{
    document.getElementById('count').textContent='Error: '+e.message;
  }}
}}

document.addEventListener('keydown',e=>{{
  if(e.key==='Escape') window.close();
}});

render();
document.getElementById('search').focus();
</script>
</body>
</html>"""


# ── HTTP handler ──────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    _html: str = ""
    def log_message(self, *a): pass

    def do_GET(self):
        body = self.__class__._html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            cmd = json.loads(raw)
            result = _execute_command(cmd)
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        resp = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


# ── Hot corner detector ───────────────────────────────────────────────────────
class HotCorner:
    def __init__(self, on_trigger):
        self._cb = on_trigger
        self._running = False
        self._last = 0
        self._sensitivity = 6    # pixels from corner
        self._debounce_ms = 800  # minimum gap between triggers

    def start(self):
        self._running = True
        threading.Thread(target=self._poll, daemon=True).start()

    def stop(self):
        self._running = False

    def _poll(self):
        user32 = ctypes.windll.user32
        while self._running:
            time.sleep(0.05)  # 50ms = 20Hz
            try:
                x, y = win32api.GetCursorPos()
                sw = user32.GetSystemMetrics(0)  # screen width
                s = self._sensitivity
                # Top-right corner
                if x >= sw - s and y <= s:
                    now = time.time() * 1000
                    if now - self._last > self._debounce_ms:
                        self._last = now
                        self._cb()
            except Exception:
                pass


# ── Startup registry ──────────────────────────────────────────────────────────
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LawrenceCornerLaunch"

def _startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except: return False

def _enable_startup():
    pw = str(Path(sys.executable).with_name("pythonw.exe"))
    cmd = f'"{pw}" "{SCRIPT_DIR / "corner_launch.py"}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)

def _disable_startup():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
    except: pass


# ── Main app ──────────────────────────────────────────────────────────────────
class CornerLaunch:
    def __init__(self):
        self._commands = _load_commands()
        self._server_port = 0
        self._chromium = _find_chromium()
        self._overlay_open = False

        # Start HTTP server
        html = _make_overlay_html(self._commands)
        handler = type("_H", (_Handler,), {"_html": html})
        self._httpd = HTTPServer(("127.0.0.1", 0), handler)
        self._server_port = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

        # Start hot corner
        self._corner = HotCorner(self._on_corner)
        self._corner.start()

        # Auto-enable startup
        if not _startup_enabled():
            try: _enable_startup()
            except: pass

    def _on_corner(self):
        if not self._overlay_open:
            self._show_overlay()

    def _show_overlay(self):
        self._overlay_open = True
        url = f"http://127.0.0.1:{self._server_port}/"
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if self._chromium:
            sw = ctypes.windll.user32.GetSystemMetrics(0)
            # Position at top-right, 520×540
            x = max(0, sw - 540)
            subprocess.Popen([
                self._chromium, f"--app={url}",
                f"--window-size=520,540",
                f"--window-position={x},30",
            ], creationflags=flags)
        else:
            webbrowser.open(url)
        # Mark as closed after a delay (overlay closes itself)
        threading.Timer(2.0, self._mark_closed).start()

    def _mark_closed(self):
        self._overlay_open = False

    def _build_tray(self):
        img = PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Teal rounded square
        d.rounded_rectangle([2, 2, 62, 62], radius=12, fill="#76e3ea")
        # Dark corner arrow (top-right)
        d.polygon([(34, 8), (56, 8), (56, 30)], fill="#0d1117")
        d.polygon([(38, 12), (52, 12), (52, 26)], fill="#76e3ea")
        d.polygon([(42, 16), (52, 16), (52, 26)], fill="#0d1117")

        startup_lbl = ("✓ Start with Windows" if _startup_enabled()
                       else "   Start with Windows")

        menu = pystray.Menu(
            pystray.MenuItem(f"CornerLaunch v{__version__}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Overlay",  lambda: self._show_overlay()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(startup_lbl,     lambda: (
                _disable_startup() if _startup_enabled() else _enable_startup()
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",          lambda: self._quit()),
        )
        self._tray = pystray.Icon("cornerlch", img,
                                   f"CornerLaunch v{__version__}", menu)
        self._tray.run()  # blocking — runs on main thread

    def _quit(self):
        self._corner.stop()
        self._httpd.shutdown()
        self._tray.stop()

    def run(self):
        self._build_tray()


if __name__ == "__main__":
    CornerLaunch().run()
