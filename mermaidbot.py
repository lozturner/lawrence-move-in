"""
Lawrence: Move In — MermaidBot v1.1.0
Natural-language Mermaid diagram generator. Type anything, get a diagram.
Uses the claude CLI (Max subscription) by default — no API key needed.
Falls back to direct API key if the CLI is not available.
"""
__version__ = "2.0.0"
import selfclean; selfclean.ensure_single("mermaidbot.py")

import base64, io, json, os, re, subprocess, threading, tkinter as tk
import urllib.request, webbrowser, tempfile
from pathlib import Path
from tkinter import font as tkfont
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageTk
import pystray

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "mermaidbot_config.json"
HISTORY_FILE = SCRIPT_DIR / "mermaidbot_history.json"

# ── Colour palette ─────────────────────────────────────────────────────────────
BG      = "#0d1117"
BG2     = "#161b22"
BG3     = "#21262d"
FG      = "#e6edf3"
FG_DIM  = "#484f58"
BLUE    = "#79c0ff"
GREEN   = "#7ee787"
YELLOW  = "#e3b341"
PURPLE  = "#d2a8ff"
RED     = "#ff7b72"
TEAL    = "#76e3ea"

# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are MermaidBot. You produce Mermaid diagram code from natural language descriptions.

STRICT RULES — follow every one or the render will break:
1. Always start with: graph LR
2. Use ONLY square brackets for node labels: [Node Text]
3. NEVER use curly braces {}, angle brackets <>, or HTML tags inside labels
4. NEVER use <br/> or any HTML anywhere
5. Keep node label text short: 2 to 5 words maximum
6. Node IDs must be simple alphanumeric with underscores only (no spaces)
7. Detect and label relationship types:
   - One-to-one: A -->|1:1| B
   - One-to-many: A -->|1:many| B
   - Optional / dashed: A -.-> B
   - Loops / cycles: use --> back to an earlier node
   - Forks: one node pointing to multiple targets
   - Merges: multiple nodes pointing to one target
8. Return ONLY the raw Mermaid code — no fences, no backticks, no explanation, no commentary

Example of correct output:
graph LR
    user[User] -->|1:1| session[Session]
    session -->|1:many| request[Request]
    request --> auth[Auth Check]
    auth -.-> cache[Cache]
    auth --> response[Response]
"""

# ── Mermaid cleaner ────────────────────────────────────────────────────────────
def clean_mermaid(raw: str) -> str:
    """Strip fences, fix graph direction, replace curly braces with square brackets."""
    # Remove markdown fences
    raw = re.sub(r"```[\w]*\n?", "", raw)
    raw = raw.replace("```", "").strip()

    # Fix graph TD / graph TB / graph RL → graph LR
    raw = re.sub(r"^graph\s+(TD|TB|RL|BT)\b", "graph LR", raw, flags=re.MULTILINE | re.IGNORECASE)

    # Ensure it starts with graph LR
    if not re.match(r"^\s*graph\s+LR", raw, re.IGNORECASE):
        raw = "graph LR\n" + raw

    # Replace curly-brace node syntax {text} with [text]
    # Matches patterns like nodeId{some text} — replace braces with brackets
    raw = re.sub(r'\{([^}]*)\}', r'[\1]', raw)

    # Remove any <br/> or <br> remnants
    raw = re.sub(r'<br\s*/?>', ' ', raw, flags=re.IGNORECASE)

    # Remove HTML tags inside labels
    raw = re.sub(r'<[^>]+>', '', raw)

    return raw.strip()

# ── History ────────────────────────────────────────────────────────────────────
def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_history(history: list):
    try:
        trimmed = history[-100:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, indent=2, ensure_ascii=False)
    except:
        pass

# ── Model catalogue (API key mode only) ───────────────────────────────────────
MODELS = [
    ("Haiku  — fastest, cheapest",       "claude-3-5-haiku-20241022"),
    ("Sonnet — balanced",                 "claude-sonnet-4-5"),
    ("Opus   — most capable, priciest",  "claude-opus-4-5"),
]
DEFAULT_MODEL = MODELS[0][1]   # Haiku

# ── Config helpers ─────────────────────────────────────────────────────────────
def _load_cfg() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def _save_cfg(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def load_api_key() -> str:
    cfg = _load_cfg()
    key = cfg.get("api_key", "").strip()
    if key:
        return key
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()

def save_api_key(key: str):
    cfg = _load_cfg()
    cfg["api_key"] = key.strip()
    _save_cfg(cfg)

def load_model() -> str:
    return _load_cfg().get("model", DEFAULT_MODEL)

def save_model(model_id: str):
    cfg = _load_cfg()
    cfg["model"] = model_id
    _save_cfg(cfg)

# ── View diagram in browser ────────────────────────────────────────────────────
def view_diagram_in_browser(mermaid_code: str):
    """Write a temp HTML file with mermaid.js CDN and open in default browser."""
    escaped = mermaid_code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MermaidBot Diagram</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: {BG};
    color: {FG};
    font-family: Consolas, monospace;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    align-items: center;
    padding: 32px 16px;
  }}
  h1 {{
    color: {BLUE};
    font-size: 1rem;
    letter-spacing: 0.1em;
    margin-bottom: 24px;
    opacity: 0.7;
  }}
  .diagram-wrap {{
    background: {BG2};
    border: 1px solid {BG3};
    border-radius: 8px;
    padding: 32px;
    max-width: 960px;
    width: 100%;
    overflow: auto;
  }}
  .mermaid {{
    font-family: Consolas, monospace;
  }}
  pre.source {{
    margin-top: 24px;
    background: {BG3};
    border-radius: 6px;
    padding: 16px;
    font-size: 0.8rem;
    color: {GREEN};
    overflow-x: auto;
    white-space: pre;
    max-width: 960px;
    width: 100%;
  }}
</style>
</head>
<body>
<h1>MermaidBot v{__version__}</h1>
<div class="diagram-wrap">
  <div class="mermaid">
{mermaid_code}
  </div>
</div>
<pre class="source">{escaped}</pre>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'dark',
    themeVariables: {{
      background: '{BG}',
      primaryColor: '{BG3}',
      primaryTextColor: '{FG}',
      primaryBorderColor: '{BLUE}',
      lineColor: '{TEAL}',
      secondaryColor: '{BG2}',
      tertiaryColor: '{BG2}'
    }}
  }});
</script>
</body>
</html>"""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False,
        prefix="mermaidbot_", encoding="utf-8"
    )
    tmp.write(html)
    tmp.close()
    webbrowser.open(f"file:///{tmp.name.replace(chr(92), '/')}")

# ── CLI bridge detection ───────────────────────────────────────────────────────
_CLI_AVAILABLE: bool | None = None   # cached after first check
_CLI_PATH: str = ""                  # full path once found

def _find_claude_exe() -> str:
    """Return full path to the claude CLI, or '' if not found."""
    import glob as _glob
    # 1. Try plain 'claude' on PATH first
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        r = subprocess.run(["claude", "--version"], capture_output=True,
                           text=True, timeout=5, creationflags=flags)
        if r.returncode == 0:
            return "claude"
    except Exception:
        pass
    # 2. Known install location: %APPDATA%\Claude\claude-code\*\claude.exe
    base = os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code")
    if os.path.isdir(base):
        hits = sorted(_glob.glob(os.path.join(base, "*", "claude.exe")), reverse=True)
        if hits:
            return hits[0]   # newest version first
    # 3. Give up
    return ""

def _check_cli() -> bool:
    """Return True if the claude CLI is available (uses Max subscription)."""
    global _CLI_AVAILABLE, _CLI_PATH
    if _CLI_AVAILABLE is not None:
        return _CLI_AVAILABLE
    _CLI_PATH = _find_claude_exe()
    if _CLI_PATH:
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            r = subprocess.run([_CLI_PATH, "--version"], capture_output=True,
                               text=True, timeout=6, creationflags=flags)
            _CLI_AVAILABLE = (r.returncode == 0)
        except Exception:
            _CLI_AVAILABLE = False
    else:
        _CLI_AVAILABLE = False
    return _CLI_AVAILABLE

# ── CLI path: uses Max subscription, no separate API key ──────────────────────
def _call_via_cli(prompt: str, callback):
    """Fire-and-forget thread — uses the `claude` CLI (Max subscription)."""
    def _work():
        try:
            full = (
                f"{SYSTEM_PROMPT}\n\n"
                f"User request: {prompt}\n\n"
                f"Reply with ONLY the raw Mermaid code. No fences, no explanation."
            )
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            exe = _CLI_PATH or "claude"
            r = subprocess.run(
                [exe, "-p", full],
                capture_output=True, text=True, timeout=60,
                creationflags=flags,
            )
            if r.returncode != 0:
                err = (r.stderr or "").strip()[:200] or "CLI returned non-zero"
                callback(None, f"Claude CLI error: {err}")
                return
            raw = r.stdout.strip()
            callback(clean_mermaid(raw), None)
        except FileNotFoundError:
            # CLI disappeared — retry via API key
            _call_via_api(prompt, callback)
        except subprocess.TimeoutExpired:
            callback(None, "Timed out waiting for claude CLI (60 s)")
        except Exception as e:
            callback(None, f"CLI error: {str(e)[:120]}")
    threading.Thread(target=_work, daemon=True).start()

# ── API-key path: for distribution / selling ──────────────────────────────────
def _call_via_api(prompt: str, callback):
    """Fire-and-forget thread — direct Anthropic API (requires key)."""
    def _work():
        api_key = load_api_key()
        if not api_key:
            callback(None, "No API key — click the key icon to add one.")
            return
        try:
            body = json.dumps({
                "model": load_model(),
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                raw = data["content"][0]["text"].strip()
                callback(clean_mermaid(raw), None)
        except urllib.error.HTTPError as e:
            try:
                body_text = e.read().decode()[:120]
            except:
                body_text = ""
            callback(None, f"HTTP {e.code}: {body_text}")
        except Exception as e:
            callback(None, f"API error: {str(e)[:100]}")
    threading.Thread(target=_work, daemon=True).start()

# ── Unified entry point ────────────────────────────────────────────────────────
def ask_claude(prompt: str, callback):
    """CLI first (Max sub, free), API key as fallback."""
    if _check_cli():
        _call_via_cli(prompt, callback)
    else:
        _call_via_api(prompt, callback)

# ── API key dialog ─────────────────────────────────────────────────────────────
def show_api_key_dialog(parent, on_save):
    dlg = tk.Toplevel(parent)
    dlg.title("API Key")
    dlg.configure(bg=BG2)
    dlg.resizable(False, False)
    dlg.grab_set()

    # Center on parent
    parent.update_idletasks()
    px = parent.winfo_x() + parent.winfo_width() // 2
    py = parent.winfo_y() + parent.winfo_height() // 2
    dlg.geometry(f"380x160+{px - 190}+{py - 80}")

    tk.Label(dlg, text="Anthropic API Key", font=("Consolas", 10, "bold"),
             fg=BLUE, bg=BG2).pack(pady=(18, 4))
    tk.Label(dlg, text="Optional — only needed if distributing without Claude Code",
             font=("Consolas", 8), fg=FG_DIM, bg=BG2).pack()

    entry_frame = tk.Frame(dlg, bg=BG2, padx=16, pady=10)
    entry_frame.pack(fill="x")
    entry = tk.Entry(entry_frame, font=("Consolas", 9), bg=BG3, fg=FG,
                     insertbackground=BLUE, relief="flat",
                     highlightthickness=1, highlightbackground=BG3,
                     highlightcolor=BLUE, show="*")
    entry.pack(fill="x", ipady=5)
    entry.focus_set()

    btn_row = tk.Frame(dlg, bg=BG2, padx=16)
    btn_row.pack(fill="x")

    def _save():
        key = entry.get().strip()
        if key:
            save_api_key(key)
            on_save()
            dlg.destroy()
        else:
            entry.config(highlightbackground=RED)

    def _cancel():
        dlg.destroy()

    tk.Button(btn_row, text="Save", font=("Consolas", 9, "bold"),
              fg=BG, bg=GREEN, relief="flat", padx=18, pady=4,
              cursor="hand2", command=_save).pack(side="right", padx=(4, 0))
    tk.Button(btn_row, text="Cancel", font=("Consolas", 9),
              fg=FG_DIM, bg=BG3, relief="flat", padx=12, pady=4,
              cursor="hand2", command=_cancel).pack(side="right")

    entry.bind("<Return>", lambda e: _save())
    entry.bind("<Escape>", lambda e: _cancel())

# ── Chromium app-mode launcher ────────────────────────────────────────────────
_CHROMIUM_EXE = ""

def _find_chromium_for_app() -> str:
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

def _get_chromium() -> str:
    global _CHROMIUM_EXE
    if not _CHROMIUM_EXE:
        _CHROMIUM_EXE = _find_chromium_for_app()
    return _CHROMIUM_EXE

# ── Diagram HTML generator ────────────────────────────────────────────────────
def _make_diagram_html(mermaid_code: str) -> str:  # noqa: C901
    # Escape for JS template literal
    js_code = (mermaid_code
               .replace("\\", "\\\\")
               .replace("`", "\\`")
               .replace("$", "\\$"))
    ver = __version__

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MermaidBot v{ver} — Diagram</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--bg4:#30363d;
  --fg:#e6edf3;--dim:#6e7681;--dim2:#484f58;
  --blue:#79c0ff;--green:#7ee787;--yellow:#e3b341;
  --red:#ff7b72;--teal:#76e3ea;--purple:#d2a8ff;
}}
html,body{{height:100%;overflow:hidden;background:var(--bg);color:var(--fg);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px}}

/* ── Toolbar ── */
#toolbar{{
  -webkit-app-region:drag;
  height:40px;background:var(--bg2);
  border-bottom:1px solid var(--bg3);
  display:flex;align-items:center;gap:4px;padding:0 8px;
  user-select:none;z-index:100;position:relative;
}}
#toolbar *{{-webkit-app-region:no-drag}}
.tb-brand{{color:var(--teal);font-weight:700;font-size:13px;letter-spacing:.04em}}
.tb-ver{{color:var(--dim2);font-size:10px;margin-right:2px}}
.sep{{width:1px;height:22px;background:var(--bg3);margin:0 4px;flex-shrink:0}}
.tb-spacer{{flex:1;-webkit-app-region:drag}}

/* ── Buttons ── */
.btn{{
  background:none;border:none;color:var(--dim);cursor:pointer;
  padding:3px 7px;border-radius:5px;font-size:12px;line-height:1;
  transition:color .12s,background .12s;white-space:nowrap;
}}
.btn:hover{{color:var(--fg);background:var(--bg3)}}
.btn.active{{color:var(--blue)}}
.btn.danger:hover{{color:var(--red);background:#2d1117}}
.btn.ok:hover{{color:var(--green)}}
.btn.warn:hover{{color:var(--yellow)}}
select.tb-sel{{
  background:var(--bg3);color:var(--fg);border:1px solid var(--bg4);
  border-radius:5px;padding:2px 6px;font-size:11px;cursor:pointer;
  outline:none;
}}
select.tb-sel:hover{{border-color:var(--blue)}}
#anim-ctr{{color:var(--dim2);font-size:10px;min-width:36px;text-align:center}}

/* ── Drag mode toggle (pill) ── */
#btn-drag{{
  background:none;
  border:2px solid var(--dim2);
  color:var(--dim);
  cursor:pointer;
  padding:4px 12px;
  border-radius:20px;
  font-size:12px;
  font-weight:600;
  line-height:1;
  transition:color .15s,border-color .15s,background .15s;
  white-space:nowrap;
}}
#btn-drag:hover{{border-color:var(--yellow);color:var(--yellow)}}
#btn-drag.active{{
  border-color:var(--yellow);
  color:var(--yellow);
  background:rgba(227,179,65,.1);
  box-shadow:0 0 8px rgba(227,179,65,.3);
}}

/* ── Lock + Export button ── */
#btn-lock{{
  display:none;
  background:none;
  border:1.5px solid var(--teal);
  color:var(--teal);
  cursor:pointer;
  padding:3px 10px;
  border-radius:20px;
  font-size:11px;
  font-weight:600;
  line-height:1;
  transition:background .15s;
  white-space:nowrap;
}}
#btn-lock:hover{{background:rgba(118,227,234,.12)}}

/* ── Diagram area ── */
#diagram-area{{
  width:100%;height:calc(100vh - 62px);overflow:hidden;
  position:relative;background:var(--bg);
}}
#pz-wrap{{
  width:100%;height:100%;
  display:flex;align-items:center;justify-content:center;
  cursor:grab;
}}
#pz-wrap:active{{cursor:grabbing}}
#pz-inner{{transform-origin:0 0;will-change:transform}}

/* ── Drag-mode active states ── */
body.drag-active #pz-wrap{{cursor:default}}
.drag-active .mm-node{{cursor:move!important}}
.drag-active .mm-node:hover rect,
.drag-active .mm-node:hover circle,
.drag-active .mm-node:hover polygon{{stroke:var(--blue);stroke-width:2}}

/* ── Mermaid SVG overrides ── */
.mermaid svg{{max-width:none!important;font-family:inherit}}
.mermaid .node rect,.mermaid .node circle,.mermaid .node polygon,
.mermaid .node ellipse,.mermaid .node path{{cursor:pointer}}
.mm-node-hover rect,.mm-node-hover circle,.mm-node-hover polygon{{
  filter:brightness(1.35);
}}

/* ── Animations ── */
.mm-anim-hidden{{opacity:0;transition:opacity .45s ease}}
.mm-anim-visible{{opacity:1;transition:opacity .45s ease}}

@keyframes mm-pulse{{
  0%,100%{{filter:drop-shadow(0 0 3px var(--blue)) drop-shadow(0 0 0px transparent)}}
  50%{{filter:drop-shadow(0 0 10px var(--blue)) drop-shadow(0 0 18px #79c0ff55)}}
}}
.mm-key-node{{animation:mm-pulse 1.8s ease-in-out infinite}}

@keyframes mm-outline-pulse{{
  0%,100%{{stroke:var(--blue);stroke-width:2;opacity:.9}}
  50%{{stroke:var(--blue);stroke-width:5;opacity:.5}}
}}

/* ── Status bar ── */
#statusbar{{
  position:fixed;bottom:0;left:0;right:0;height:22px;
  background:var(--bg2);border-top:1px solid var(--bg3);
  display:flex;align-items:center;padding:0 10px;gap:16px;
  font-size:10px;color:var(--dim2);z-index:100;
}}
#sb-status{{color:var(--dim)}}
#sb-hint{{margin-left:auto;color:var(--dim2)}}

/* ── Node tooltip ── */
#tooltip{{
  position:fixed;bottom:26px;left:10px;
  background:var(--bg3);border:1px solid var(--bg4);
  border-radius:6px;padding:4px 10px;font-size:11px;
  color:var(--teal);pointer-events:none;
  opacity:0;transition:opacity .15s;z-index:200;
}}
#tooltip.show{{opacity:1}}

/* ── Node edit input ── */
#node-edit-input{{
  display:none;
  position:fixed;
  z-index:300;
  background:var(--bg3);
  border:2px solid var(--blue);
  color:var(--fg);
  border-radius:5px;
  padding:3px 8px;
  font-size:13px;
  font-family:'Segoe UI',system-ui,sans-serif;
  outline:none;
  box-shadow:0 2px 12px rgba(121,192,255,.3);
  min-width:80px;
}}

/* ── Edit panel ── */
#edit-panel{{
  position:fixed;
  bottom:22px;
  left:0;right:0;
  z-index:90;
  background:var(--bg2);
  border-top:1px solid var(--bg3);
  transform:translateY(100%);
  transition:transform .25s ease;
  padding:8px 12px 10px;
}}
#edit-panel.open{{transform:translateY(0)}}
.edit-panel-header{{
  display:flex;align-items:center;gap:8px;margin-bottom:6px;
}}
.edit-panel-title{{
  font-size:12px;font-weight:600;color:var(--teal);flex:1;
}}
#edit-code{{
  width:100%;height:140px;
  background:#0d1f0f;
  color:var(--green);
  border:1px solid var(--bg4);
  border-radius:5px;
  font-family:Consolas,monospace;
  font-size:12px;
  padding:6px 8px;
  resize:vertical;
  outline:none;
  line-height:1.5;
}}
#edit-code:focus{{border-color:var(--blue)}}
#edit-toast{{
  font-size:10px;color:var(--dim);margin-top:4px;min-height:14px;
  transition:opacity .3s;
}}

/* ── Close confirmation modal ── */
#modal-close{{
  display:none;
  position:fixed;inset:0;
  z-index:500;
  background:rgba(0,0,0,.7);
  backdrop-filter:blur(4px);
  align-items:center;justify-content:center;
}}
#modal-close.open{{display:flex}}
.modal-box{{
  background:var(--bg2);
  border:1px solid var(--bg4);
  border-radius:12px;
  padding:28px 32px;
  max-width:380px;width:90%;
  text-align:center;
  box-shadow:0 16px 48px rgba(0,0,0,.6);
}}
.modal-title{{
  font-size:18px;font-weight:700;color:var(--fg);margin-bottom:6px;
}}
.modal-sub{{
  font-size:12px;color:var(--dim);margin-bottom:22px;
}}
.modal-btns{{
  display:flex;flex-direction:column;gap:8px;
}}
.modal-btn{{
  width:100%;padding:9px 16px;border-radius:7px;
  font-size:13px;font-weight:600;cursor:pointer;
  border:none;transition:opacity .15s,background .15s;
}}
.modal-btn:hover{{opacity:.85}}
.modal-btn.primary{{background:var(--blue);color:#0d1117}}
.modal-btn.secondary{{background:var(--bg3);color:var(--fg);border:1px solid var(--bg4)}}
.modal-btn.danger{{background:var(--red);color:#fff}}
.modal-btn.ghost{{background:none;color:var(--dim);border:1px solid var(--bg4)}}
</style>
</head>
<body>

<div id="toolbar">
  <span class="tb-brand">MM</span>
  <span class="tb-ver">v{ver}</span>
  <div class="sep"></div>

  <select class="tb-sel" id="font-sel" title="Font" onchange="changeFont(this.value)">
    <option value="'Segoe UI',system-ui">Segoe UI</option>
    <option value="Consolas,monospace">Consolas</option>
    <option value="Georgia,serif">Georgia</option>
    <option value="'Arial',sans-serif">Arial</option>
    <option value="'Trebuchet MS',sans-serif">Trebuchet</option>
  </select>

  <select class="tb-sel" id="theme-sel" title="Theme" onchange="changeTheme(this.value)">
    <option value="dark">dark</option>
    <option value="default" selected>light</option>
    <option value="forest">forest</option>
    <option value="neutral">neutral</option>
  </select>

  <div class="sep"></div>

  <button class="btn" title="First"       onclick="animFirst()">⏮</button>
  <button class="btn" title="Step back"   onclick="animBack()">⏪</button>
  <button class="btn" id="btn-play" title="Play / Pause" onclick="animToggle()">▶</button>
  <button class="btn" title="Step fwd"    onclick="animFwd()">⏩</button>
  <button class="btn" title="Last"        onclick="animLast()">⏭</button>
  <button class="btn" id="btn-loop" title="Loop" onclick="toggleLoop()">🔁</button>
  <button class="btn" title="Replay"      onclick="animReplay()">↺</button>
  <span id="anim-ctr">—/—</span>

  <div class="sep"></div>

  <button id="btn-drag" title="Toggle drag-to-reposition mode" onclick="toggleDragMode()">✦ Edit Layout</button>
  <button id="btn-lock" title="Lock layout and export JSON"    onclick="lockAndExport()">🔒 Lock + Export</button>

  <div class="sep"></div>

  <button class="btn" title="Edit code panel" onclick="toggleEditPanel()">✏</button>

  <div class="sep"></div>

  <button class="btn ok"   title="Save PNG"    onclick="savePng()">💾 PNG</button>
  <button class="btn"      title="Copy SVG+JS" onclick="copySvgJs()">⟨/⟩ SVG</button>
  <button class="btn"      title="Copy code"   onclick="copyCode()">📋 Code</button>

  <div class="tb-spacer"></div>

  <button class="btn warn"   title="Minimise"  onclick="window.minimize&&window.minimize()">−</button>
  <button class="btn ok"     id="btn-max" title="Maximise" onclick="toggleMax()">□</button>
  <button class="btn danger" title="Close"     onclick="showCloseModal()">×</button>
</div>

<div id="diagram-area">
  <div id="pz-wrap">
    <div id="pz-inner">
      <div class="mermaid" id="mm-root"></div>
    </div>
  </div>
</div>

<div id="statusbar">
  <span id="sb-status">Rendering…</span>
  <span id="sb-hint">Scroll = zoom · Drag = pan · Dbl-click = reset · Click node = info</span>
</div>
<div id="tooltip"></div>

<!-- Node edit input (in-place label editing) -->
<input id="node-edit-input" type="text" />

<!-- Edit panel -->
<div id="edit-panel">
  <div class="edit-panel-header">
    <span class="edit-panel-title">✏ Edit Code</span>
    <button class="btn ok" onclick="regenDiagram()" title="Re-render diagram from textarea">↺ Regen</button>
    <button class="btn" onclick="sendEditCode()" title="Copy code to clipboard">→ Send</button>
    <button class="btn" onclick="toggleEditPanel()" title="Collapse">▾</button>
  </div>
  <textarea id="edit-code" spellcheck="false">{js_code}</textarea>
  <div id="edit-toast"></div>
</div>

<!-- Close confirmation modal -->
<div id="modal-close">
  <div class="modal-box">
    <div class="modal-title">Before you go…</div>
    <div class="modal-sub">Unsaved diagrams are gone for good.</div>
    <div class="modal-btns">
      <button class="modal-btn primary"    onclick="savePng();closeModal()">💾 Save PNG</button>
      <button class="modal-btn secondary"  onclick="copySvgJs();closeModal()">⟨/⟩ Copy SVG</button>
      <button class="modal-btn secondary"  onclick="copyCode();closeModal()">📋 Copy Code</button>
      <button class="modal-btn danger"     onclick="window.close()">Close anyway</button>
      <button class="modal-btn ghost"      onclick="closeModal()">Cancel</button>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
// ════════════════════════════════════════════════════════════════════════
//  MermaidBot Diagram Player  v{ver}
//  Namespace: mmDiagram  |  All nodes: data-mm-node-id, .mm-node
// ════════════════════════════════════════════════════════════════════════
const MM_VERSION = "{ver}";
const MM_NS      = "mmDiagram";
const MM_SOURCE  = `{js_code}`;

// ── Export data object (populated after render) ───────────────────────
const mmDiagram = {{
  version : MM_VERSION,
  ns      : MM_NS,
  source  : MM_SOURCE,
  nodes   : [],
  edges   : [],
  get svg(){{ return document.querySelector('#mm-root svg')?.outerHTML || ''; }},
}};

// ── Graph State for drag mode ─────────────────────────────────────────
const GS = {{
  nodes    : new Map(),   // svgNodeId -> {{el, tx, ty, w, h, label, mmId}}
  edges    : [],          // [{{pathEl, labelEl, srcId, tgtId, edgeLabel, dashed}}]
  dragMode : false,
  dragging : null,
}};

// ── Mermaid config ────────────────────────────────────────────────────
let _theme = 'dark';
let _font  = "'Segoe UI',system-ui";

function mmConfig(theme){{
  return {{
    startOnLoad: false, theme,
    themeVariables: {{
      background:'#0d1117', primaryColor:'#21262d',
      primaryTextColor:'#e6edf3', primaryBorderColor:'#79c0ff',
      lineColor:'#76e3ea', secondaryColor:'#161b22',
      tertiaryColor:'#161b22', edgeLabelBackground:'#21262d',
      fontFamily:_font, fontSize:'14px',
    }},
    securityLevel:'loose',
    flowchart:{{ curve:'basis', useMaxWidth:false }},
  }};
}}

// ── Render ────────────────────────────────────────────────────────────
async function renderDiagram(theme){{
  _theme = theme || _theme;
  mermaid.initialize(mmConfig(_theme));
  const el = document.getElementById('mm-root');
  el.innerHTML = '';
  mmDiagram.nodes = [];
  mmDiagram.edges = [];
  GS.nodes.clear();
  GS.edges = [];
  try {{
    const uid = MM_NS + '_' + Date.now();
    const {{svg}} = await mermaid.render(uid, MM_SOURCE);
    el.innerHTML = svg;
    postProcess(el);
    buildAnimSeq();
    showAll();
    buildGraphState();
    status('Ready  ·  v' + MM_VERSION);
  }} catch(e) {{
    el.innerHTML = `<div style="color:#ff7b72;padding:24px;font-family:monospace">⚠ Render error:<br><pre>${{e.message}}</pre></div>`;
    status('Render error — check code', true);
  }}
}}

async function regenDiagram(){{
  const src = document.getElementById('edit-code').value.trim();
  if(!src) return;
  mermaid.initialize(mmConfig(_theme));
  const el = document.getElementById('mm-root');
  el.innerHTML = '';
  mmDiagram.nodes = [];
  mmDiagram.edges = [];
  GS.nodes.clear();
  GS.edges = [];
  try {{
    const uid = MM_NS + '_regen_' + Date.now();
    const {{svg}} = await mermaid.render(uid, src);
    el.innerHTML = svg;
    postProcess(el);
    buildAnimSeq();
    showAll();
    buildGraphState();
    status('Re-rendered from edit panel');
    showEditToast('Diagram updated!');
  }} catch(e) {{
    status('Regen error: ' + e.message, true);
    showEditToast('Error: ' + e.message);
  }}
}}

function sendEditCode(){{
  const src = document.getElementById('edit-code').value;
  navigator.clipboard.writeText(src).then(()=>{{
    showEditToast('Copied to clipboard — paste into MermaidBot');
  }});
}}

function showEditToast(msg){{
  const t = document.getElementById('edit-toast');
  t.textContent = msg;
  t.style.opacity = '1';
  clearTimeout(t._tid);
  t._tid = setTimeout(()=>{{ t.style.opacity='0'; }}, 3500);
}}

// ── SVG post-processing ───────────────────────────────────────────────
function postProcess(container){{
  const svg = container.querySelector('svg');
  if(!svg) return;
  svg.setAttribute('data-mm-ns', MM_NS);
  svg.removeAttribute('height');

  const nodes = [...svg.querySelectorAll('.node')];
  nodes.forEach((n,i)=>{{
    const nid = MM_NS + '_node_' + i;
    n.classList.add('mm-node');
    n.setAttribute('data-mm-node-id', nid);
    n.setAttribute('data-mm-index', i);
    n.style.cursor = 'pointer';
    const label = (n.querySelector('.label,text,.nodeLabel') || n)
                    .textContent.trim().replace(/\s+/g,' ');
    mmDiagram.nodes.push({{id:nid, index:i, label}});
    n.addEventListener('click',    ()=> onNodeClick(n, i));
    n.addEventListener('mouseenter',()=> onNodeHover(n, true));
    n.addEventListener('mouseleave',()=> onNodeHover(n, false));
    n.addEventListener('dblclick',  (e)=> onNodeDblClick(e, n, nid));
  }});

  const edges = [...svg.querySelectorAll('.edgePath,.edge')];
  edges.forEach((e,i)=>{{
    const eid = MM_NS + '_edge_' + i;
    e.classList.add('mm-edge');
    e.setAttribute('data-mm-edge-id', eid);
    mmDiagram.edges.push({{id:eid, index:i}});
  }});

  markKeyNode(nodes);
}}

function markKeyNode(nodes){{
  if(!nodes.length) return;
  const src = MM_SOURCE;
  const outgoing = new Set();
  const allIds   = new Set();
  src.split('\n').forEach(line=>{{
    const m = line.match(/([\w]+)(?:\[[^\]]*\]|\([^)]*\))?\s*-+>+(?:\|[^|]*\|)?\s*([\w]+)/);
    if(m){{ outgoing.add(m[1]); allIds.add(m[1]); allIds.add(m[2]); }}
  }});
  const terminals = [...allIds].filter(id=>!outgoing.has(id));
  let keyNode = nodes[nodes.length-1];
  if(terminals.length){{
    for(const n of [...nodes].reverse()){{
      const lbl = (n.querySelector('.label,text,.nodeLabel')||n).textContent.trim().toLowerCase();
      if(terminals.some(t=>lbl.includes(t.toLowerCase()))){{ keyNode=n; break; }}
    }}
  }}
  keyNode.classList.add('mm-key-node');
  keyNode.setAttribute('data-mm-key','true');
  const rect = keyNode.querySelector('rect,circle,polygon,ellipse');
  if(rect) rect.style.animation = 'mm-outline-pulse 1.8s ease-in-out infinite';
}}

// ── Node interaction ──────────────────────────────────────────────────
function onNodeClick(node, i){{
  if(GS.dragMode) return;
  const info = mmDiagram.nodes[i] || {{}};
  tooltip(`Node ${{i+1}}: ${{info.label||'?'}}`);
  status(`Clicked: ${{info.label||'node '+i}}`);
}}
function onNodeHover(node, enter){{
  if(!GS.dragMode) node.style.filter = enter ? 'brightness(1.3)' : '';
}}
function onNodeDblClick(e, node, nodeId){{
  if(!GS.dragMode) return;
  e.stopPropagation();
  enableNodeEdit(node, nodeId);
}}
function tooltip(msg){{
  const t = document.getElementById('tooltip');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._tid);
  t._tid = setTimeout(()=>t.classList.remove('show'), 3000);
}}

// ── Build graph state ─────────────────────────────────────────────────
function buildGraphState(){{
  GS.nodes.clear();
  GS.edges = [];
  const svg = document.querySelector('#mm-root svg');
  if(!svg) return;

  // Collect nodes
  svg.querySelectorAll('.mm-node').forEach(el=>{{
    const nid = el.getAttribute('data-mm-node-id');
    const bb  = el.getBBox();
    const tf  = el.getAttribute('transform') || '';
    const m   = tf.match(/translate\(\s*([\-\d.]+)[\s,]+([\-\d.]+)\s*\)/);
    const tx  = m ? parseFloat(m[1]) : 0;
    const ty  = m ? parseFloat(m[2]) : 0;
    const labelEl = el.querySelector('.label,text,.nodeLabel');
    const label   = labelEl ? labelEl.textContent.trim().replace(/\s+/g,' ') : '';
    // best-guess mermaid ID = first word of label or data attribute
    const mmId = label.split(/\s+/)[0] || nid;
    GS.nodes.set(nid, {{el, tx, ty, w:bb.width, h:bb.height, label, mmId}});
  }});

  // Parse edges from source
  const edgeRe = /(\w+)(?:\[[^\]]*\])?\s*(-+>+|-*\.->+)\s*(?:\|([^|]*)\|)?\s*(\w+)/g;
  let em;
  const src = MM_SOURCE;
  while((em = edgeRe.exec(src)) !== null){{
    const [, srcMmId, arrow, edgeLabel='', tgtMmId] = em;
    const dashed = arrow.includes('.');
    // find node entries by mmId match
    let srcEntry = null, tgtEntry = null;
    for(const [nid, nd] of GS.nodes){{
      if(nd.mmId.toLowerCase() === srcMmId.toLowerCase()) srcEntry = nid;
      if(nd.mmId.toLowerCase() === tgtMmId.toLowerCase()) tgtEntry = nid;
    }}
    // fallback: label text contains the id
    if(!srcEntry || !tgtEntry){{
      for(const [nid, nd] of GS.nodes){{
        if(!srcEntry && nd.label.toLowerCase().includes(srcMmId.toLowerCase())) srcEntry = nid;
        if(!tgtEntry && nd.label.toLowerCase().includes(tgtMmId.toLowerCase())) tgtEntry = nid;
      }}
    }}
    if(!srcEntry || !tgtEntry) continue;
    // find matching SVG edge path (by order or best effort)
    const edgePaths = [...document.querySelectorAll('#mm-root .mm-edge path,#mm-root .mm-edge .path')];
    const pathEl = edgePaths[GS.edges.length] || null;
    GS.edges.push({{pathEl, labelEl:null, srcId:srcEntry, tgtId:tgtEntry, edgeLabel, dashed}});
  }}
}}

// ── Drag mode ─────────────────────────────────────────────────────────
function toggleDragMode(){{
  GS.dragMode = !GS.dragMode;
  const btn = document.getElementById('btn-drag');
  const lock = document.getElementById('btn-lock');
  btn.classList.toggle('active', GS.dragMode);
  lock.style.display = GS.dragMode ? 'inline-block' : 'none';
  document.body.classList.toggle('drag-active', GS.dragMode);

  const svg = document.querySelector('#mm-root svg');
  if(!svg) return;

  if(GS.dragMode){{
    svg.querySelectorAll('.mm-node').forEach(el=>{{
      el._dragDown = (e)=>startNodeDrag(e, el);
      el.addEventListener('mousedown', el._dragDown);
    }});
    status('Drag mode ON — drag nodes to reposition, dbl-click to rename');
  }} else {{
    svg.querySelectorAll('.mm-node').forEach(el=>{{
      if(el._dragDown) el.removeEventListener('mousedown', el._dragDown);
    }});
    status('Drag mode OFF');
  }}
}}

function startNodeDrag(e, el){{
  if(!GS.dragMode) return;
  e.preventDefault();
  e.stopPropagation();
  const svg  = document.querySelector('#mm-root svg');
  const ctm  = svg.getScreenCTM().inverse();
  const pt   = svg.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const svgPt = pt.matrixTransform(ctm);
  const nid   = el.getAttribute('data-mm-node-id');
  const nd    = GS.nodes.get(nid);
  GS.dragging = {{
    nid, el,
    startSvgX : svgPt.x,
    startSvgY : svgPt.y,
    startTx   : nd ? nd.tx : 0,
    startTy   : nd ? nd.ty : 0,
  }};
  const mm = (ev)=>doNodeDrag(ev);
  const mu = ()=>endNodeDrag(mm, mu);
  GS.dragging._mm = mm;
  GS.dragging._mu = mu;
  document.addEventListener('mousemove', mm);
  document.addEventListener('mouseup',   mu);
}}

function doNodeDrag(e){{
  if(!GS.dragging) return;
  const svg = document.querySelector('#mm-root svg');
  const ctm = svg.getScreenCTM().inverse();
  const pt  = svg.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const sp  = pt.matrixTransform(ctm);
  const d   = GS.dragging;
  const newTx = d.startTx + (sp.x - d.startSvgX);
  const newTy = d.startTy + (sp.y - d.startSvgY);
  d.el.setAttribute('transform', `translate(${{newTx}},${{newTy}})`);
  const nd = GS.nodes.get(d.nid);
  if(nd){{ nd.tx = newTx; nd.ty = newTy; }}
  redrawEdgesForNode(d.nid);
}}

function endNodeDrag(mm, mu){{
  GS.dragging = null;
  document.removeEventListener('mousemove', mm);
  document.removeEventListener('mouseup',   mu);
}}

function getNodeCenter(nid){{
  const nd = GS.nodes.get(nid);
  if(!nd) return null;
  return {{x:nd.tx, y:nd.ty, w:nd.w, h:nd.h}};
}}

function getConnectionPt(src, tgt){{
  const sx = src.x, sy = src.y, sw = src.w/2, sh = src.h/2;
  const tx = tgt.x, ty = tgt.y;
  const dx = tx - sx, dy = ty - sy;
  const ang = Math.atan2(dy, dx);
  let ex, ey;
  // clamp to source rect border
  if(Math.abs(Math.cos(ang)*sh) < Math.abs(Math.sin(ang)*sw)){{
    const sign = dy > 0 ? 1 : -1;
    ey = sy + sign*sh;
    ex = sx + (sign*sh)*(dx/dy||0);
  }} else {{
    const sign = dx > 0 ? 1 : -1;
    ex = sx + sign*sw;
    ey = sy + (sign*sw)*(dy/dx||0);
  }}
  return {{x:ex, y:ey}};
}}

function makeBezierD(sx,sy,ex,ey){{
  const mx = (sx+ex)/2;
  return `M ${{sx}},${{sy}} C ${{mx}},${{sy}} ${{mx}},${{ey}} ${{ex}},${{ey}}`;
}}

function redrawEdgesForNode(nodeId){{
  GS.edges.forEach(edge=>{{
    if(edge.srcId !== nodeId && edge.tgtId !== nodeId) return;
    if(!edge.pathEl) return;
    const srcC = getNodeCenter(edge.srcId);
    const tgtC = getNodeCenter(edge.tgtId);
    if(!srcC || !tgtC) return;
    const sp  = getConnectionPt(srcC, tgtC);
    const ep  = getConnectionPt(tgtC, srcC);
    const d   = makeBezierD(sp.x, sp.y, ep.x, ep.y);
    edge.pathEl.setAttribute('d', d);
    if(edge.labelEl){{
      const mx = (sp.x+ep.x)/2, my = (sp.y+ep.y)/2;
      edge.labelEl.setAttribute('transform',`translate(${{mx}},${{my}})`);
    }}
  }});
}}

// ── Node label editing ────────────────────────────────────────────────
function enableNodeEdit(node, nodeId){{
  const inp = document.getElementById('node-edit-input');
  const nd  = GS.nodes.get(nodeId);
  if(!nd) return;
  const br  = node.getBoundingClientRect();
  inp.style.display = 'block';
  inp.style.left    = br.left + 'px';
  inp.style.top     = (br.top + br.height/2 - 14) + 'px';
  inp.style.width   = Math.max(br.width, 100) + 'px';
  inp.value         = nd.label;
  inp.focus();
  inp.select();

  function commit(){{
    const newLabel = inp.value.trim() || nd.label;
    nd.label = newLabel;
    // update SVG text
    const textEl = node.querySelector('.label,text,.nodeLabel');
    if(textEl){{
      const tspan = textEl.querySelector('tspan') || textEl;
      tspan.textContent = newLabel;
    }}
    inp.style.display = 'none';
    inp.removeEventListener('keydown', onKey);
    inp.removeEventListener('blur', onBlur);
  }}

  function onKey(e){{
    if(e.key === 'Enter') commit();
    if(e.key === 'Escape'){{ inp.style.display='none'; inp.removeEventListener('keydown',onKey); inp.removeEventListener('blur',onBlur); }}
  }}
  function onBlur(){{ commit(); }}

  inp.addEventListener('keydown', onKey);
  inp.addEventListener('blur',    onBlur);
}}

// ── Lock and export layout ────────────────────────────────────────────
function lockAndExport(){{
  const nodesArr = [];
  GS.nodes.forEach((nd, nid)=>{{
    nodesArr.push({{id:nid, mmId:nd.mmId, label:nd.label, x:nd.tx, y:nd.ty, w:nd.w, h:nd.h}});
  }});
  const edgesArr = GS.edges.map(e=>{{
    const snd = GS.nodes.get(e.srcId), tnd = GS.nodes.get(e.tgtId);
    return {{from:snd?snd.mmId:e.srcId, to:tnd?tnd.mmId:e.tgtId, label:e.edgeLabel, dashed:e.dashed}};
  }});
  const layout = {{}};
  GS.nodes.forEach((nd,nid)=>{{ layout[nd.mmId] = {{x:nd.tx, y:nd.ty}}; }});
  const payload = {{
    version   : MM_VERSION,
    generated : new Date().toISOString(),
    source    : MM_SOURCE,
    nodes     : nodesArr,
    edges     : edgesArr,
    layout,
  }};
  const json = JSON.stringify(payload, null, 2);
  navigator.clipboard.writeText(json).then(()=>{{
    status(`Layout JSON copied — ${{nodesArr.length}} nodes, ${{edgesArr.length}} edges`);
    tooltip(`Layout JSON copied — ${{nodesArr.length}} nodes, ${{edgesArr.length}} edges`);
  }});
  savePng();
}}

// ── Animation ─────────────────────────────────────────────────────────
let _seq = [];
let _step = -1;
let _playing = false;
let _loop = false;
let _timer = null;
const STEP_MS = 550;

function buildAnimSeq(){{
  const svg = document.querySelector('#mm-root svg');
  if(!svg) return;
  const nodes = [...svg.querySelectorAll('.mm-node')];
  const edges = [...svg.querySelectorAll('.mm-edge')];
  _seq = [];
  const max = Math.max(nodes.length, edges.length);
  for(let i=0;i<max;i++){{
    if(nodes[i]) _seq.push(nodes[i]);
    if(edges[i]) _seq.push(edges[i]);
  }}
  _step = _seq.length - 1;
  _seq.forEach(el=>{{ el.classList.remove('mm-anim-hidden'); el.classList.add('mm-anim-visible'); }});
  stepDisplay();
}}

function applyStep(n){{
  _seq.forEach((el,i)=>{{
    if(i<=n){{ el.classList.remove('mm-anim-hidden'); el.classList.add('mm-anim-visible'); }}
    else{{     el.classList.remove('mm-anim-visible'); el.classList.add('mm-anim-hidden'); }}
  }});
  _step=n; stepDisplay();
}}
function showAll(){{
  _seq.forEach(el=>{{ el.classList.remove('mm-anim-hidden'); el.classList.add('mm-anim-visible'); }});
  _step=_seq.length-1; stepDisplay();
}}
function hideAll(){{
  _seq.forEach(el=>{{ el.classList.remove('mm-anim-visible'); el.classList.add('mm-anim-hidden'); }});
  _step=-1; stepDisplay();
}}
function stepDisplay(){{
  document.getElementById('anim-ctr').textContent =
    _seq.length ? `${{Math.max(0,_step+1)}}/${{_seq.length}}` : '—/—';
}}
function animFirst() {{ stopPlay(); hideAll(); }}
function animBack()  {{ stopPlay(); if(_step>-1) applyStep(_step-1); }}
function animFwd()   {{ stopPlay(); if(_step<_seq.length-1) applyStep(_step+1); }}
function animLast()  {{ stopPlay(); showAll(); }}
function animReplay(){{ stopPlay(); hideAll(); setTimeout(startPlay,80); }}
function toggleLoop(){{
  _loop = !_loop;
  document.getElementById('btn-loop').classList.toggle('active',_loop);
}}
function animToggle(){{ _playing ? stopPlay() : startPlay(); }}
function startPlay(){{
  if(_step>=_seq.length-1) hideAll();
  _playing = true;
  document.getElementById('btn-play').textContent = '⏸';
  document.getElementById('btn-play').classList.add('active');
  _timer = setInterval(()=>{{
    if(_step<_seq.length-1) applyStep(_step+1);
    else if(_loop) hideAll();
    else stopPlay();
  }},STEP_MS);
}}
function stopPlay(){{
  _playing = false;
  document.getElementById('btn-play').textContent = '▶';
  document.getElementById('btn-play').classList.remove('active');
  if(_timer){{ clearInterval(_timer); _timer=null; }}
}}

// ── Pan / Zoom ────────────────────────────────────────────────────────
let _scale=1, _px=0, _py=0, _panDragging=false, _lx=0, _ly=0;

function applyXform(){{
  document.getElementById('pz-inner').style.transform =
    `translate(${{_px}}px,${{_py}}px) scale(${{_scale}})`;
}}
function initPanZoom(){{
  const wrap = document.getElementById('pz-wrap');
  wrap.addEventListener('wheel', e=>{{
    e.preventDefault();
    const rect = wrap.getBoundingClientRect();
    const mx = e.clientX-rect.left, my = e.clientY-rect.top;
    const d  = e.deltaY>0 ? 0.88 : 1.14;
    const ns = Math.min(8, Math.max(0.15, _scale*d));
    _px = mx - (mx-_px)*(ns/_scale);
    _py = my - (my-_py)*(ns/_scale);
    _scale = ns; applyXform();
  }},{{passive:false}});
  wrap.addEventListener('mousedown', e=>{{
    if(GS.dragMode) return;
    if(e.target.closest('.mm-node,button,select,#edit-panel')) return;
    _panDragging=true; _lx=e.clientX; _ly=e.clientY;
  }});
  document.addEventListener('mousemove', e=>{{
    if(!_panDragging) return;
    _px += e.clientX-_lx; _py += e.clientY-_ly;
    _lx=e.clientX; _ly=e.clientY; applyXform();
  }});
  document.addEventListener('mouseup', ()=>{{ _panDragging=false; }});
  wrap.addEventListener('dblclick', e=>{{
    if(GS.dragMode) return;
    if(e.target.closest('.mm-node,button,select')) return;
    _scale=1; _px=0; _py=0; applyXform();
  }});
}}

// ── Font / Theme ──────────────────────────────────────────────────────
function changeFont(f){{
  _font = f;
  document.getElementById('pz-inner').style.fontFamily = f;
  document.querySelectorAll('#mm-root svg text,.label,.nodeLabel').forEach(el=>el.style.fontFamily=f);
}}
async function changeTheme(t){{ await renderDiagram(t); }}

// ── Maximise / Fullscreen ─────────────────────────────────────────────
function toggleMax(){{
  if(!document.fullscreenElement){{
    document.documentElement.requestFullscreen().catch(()=>{{
      window.resizeTo(screen.width,screen.height); window.moveTo(0,0);
    }});
    document.getElementById('btn-max').textContent = '❐';
  }} else {{
    document.exitFullscreen();
    document.getElementById('btn-max').textContent = '□';
  }}
}}

// ── Save PNG ──────────────────────────────────────────────────────────
function savePng(){{
  const svg = document.querySelector('#mm-root svg');
  if(!svg) return;
  const clone = svg.cloneNode(true);
  const bb = svg.getBoundingClientRect();
  const w  = Math.max(bb.width*2, 800), h = Math.max(bb.height*2, 400);
  clone.setAttribute('width',w); clone.setAttribute('height',h);
  const blob = new Blob([new XMLSerializer().serializeToString(clone)],
                        {{type:'image/svg+xml'}});
  const url  = URL.createObjectURL(blob);
  const canvas = document.createElement('canvas');
  canvas.width=w; canvas.height=h;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle='#0d1117'; ctx.fillRect(0,0,w,h);
  const img = new Image();
  img.onload = ()=>{{
    ctx.drawImage(img,0,0,w,h); URL.revokeObjectURL(url);
    const a = document.createElement('a');
    a.download = `mermaid_${{Date.now()}}.png`;
    a.href = canvas.toDataURL('image/png'); a.click();
    status('PNG saved!');
  }};
  img.src = url;
}}

// ── Copy SVG + JS wrapper ─────────────────────────────────────────────
function copySvgJs(){{
  const svg = document.querySelector('#mm-root svg');
  if(!svg) return;
  const svgStr = svg.outerHTML.replace(/`/g,'\\`');
  const out = `// ═══════════════════════════════════════════════
// MermaidBot Diagram Export — v${{MM_VERSION}}
// Generated: ${{new Date().toISOString()}}
// Namespace: ${{MM_NS}}
// ═══════════════════════════════════════════════
const ${{MM_NS}} = {{
  version : "${{MM_VERSION}}",
  source  : \`${{MM_SOURCE.replace(/`/g,'\\`')}}\`,
  nodes   : ${{JSON.stringify(mmDiagram.nodes,null,2)}},
  edges   : ${{JSON.stringify(mmDiagram.edges,null,2)}},
  svg     : \`${{svgStr}}\`,
  /** Inject into any DOM: document.getElementById('container').innerHTML = ${{MM_NS}}.svg */
}};`;
  navigator.clipboard.writeText(out)
    .then(()=>status('SVG + JS wrapper copied!'));
}}

function copyCode(){{
  navigator.clipboard.writeText(MM_SOURCE)
    .then(()=>status('Mermaid code copied!'));
}}

// ── Edit panel toggle ─────────────────────────────────────────────────
function toggleEditPanel(){{
  const p = document.getElementById('edit-panel');
  const open = p.classList.toggle('open');
  // sync textarea with current source if opening
  if(open){{
    const ta = document.getElementById('edit-code');
    if(!ta.value.trim()) ta.value = MM_SOURCE;
  }}
  status(open ? 'Edit panel open — edit and click Regen' : 'Edit panel closed');
}}

// ── Close modal ───────────────────────────────────────────────────────
function showCloseModal(){{
  document.getElementById('modal-close').classList.add('open');
}}
function closeModal(){{
  document.getElementById('modal-close').classList.remove('open');
}}
// click outside box dismisses
document.getElementById('modal-close').addEventListener('click', function(e){{
  if(e.target === this) closeModal();
}});

// ── Status helper ─────────────────────────────────────────────────────
function status(msg, err){{
  const el = document.getElementById('sb-status');
  el.textContent = msg;
  el.style.color = err ? '#ff7b72' : '#6e7681';
}}

// ── Boot ──────────────────────────────────────────────────────────────
initPanZoom();
renderDiagram('dark');
</script>
</body>
</html>"""

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False,
        prefix="mermaidbot_", encoding="utf-8"
    )
    tmp.write(html)
    tmp.close()
    webbrowser.open(f"file:///{tmp.name.replace(chr(92), '/')}")

# ── CLI bridge detection ───────────────────────────────────────────────────────
_CLI_AVAILABLE: bool | None = None   # cached after first check
_CLI_PATH: str = ""                  # full path once found

def _find_claude_exe() -> str:
    """Return full path to the claude CLI, or '' if not found."""
    import glob as _glob
    # 1. Try plain 'claude' on PATH first
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        r = subprocess.run(["claude", "--version"], capture_output=True,
                           text=True, timeout=5, creationflags=flags)
        if r.returncode == 0:
            return "claude"
    except Exception:
        pass
    # 2. Known install location: %APPDATA%\Claude\claude-code\*\claude.exe
    base = os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code")
    if os.path.isdir(base):
        hits = sorted(_glob.glob(os.path.join(base, "*", "claude.exe")), reverse=True)
        if hits:
            return hits[0]   # newest version first
    # 3. Give up
    return ""

def _check_cli() -> bool:
    """Return True if the claude CLI is available (uses Max subscription)."""
    global _CLI_AVAILABLE, _CLI_PATH
    if _CLI_AVAILABLE is not None:
        return _CLI_AVAILABLE
    _CLI_PATH = _find_claude_exe()
    if _CLI_PATH:
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            r = subprocess.run([_CLI_PATH, "--version"], capture_output=True,
                               text=True, timeout=6, creationflags=flags)
            _CLI_AVAILABLE = (r.returncode == 0)
        except Exception:
            _CLI_AVAILABLE = False
    else:
        _CLI_AVAILABLE = False
    return _CLI_AVAILABLE

# ── CLI path: uses Max subscription, no separate API key ──────────────────────
def _call_via_cli(prompt: str, callback):
    """Fire-and-forget thread — uses the `claude` CLI (Max subscription)."""
    def _work():
        try:
            full = (
                f"{SYSTEM_PROMPT}\n\n"
                f"User request: {prompt}\n\n"
                f"Reply with ONLY the raw Mermaid code. No fences, no explanation."
            )
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            exe = _CLI_PATH or "claude"
            r = subprocess.run(
                [exe, "-p", full],
                capture_output=True, text=True, timeout=60,
                creationflags=flags,
            )
            if r.returncode != 0:
                err = (r.stderr or "").strip()[:200] or "CLI returned non-zero"
                callback(None, f"Claude CLI error: {err}")
                return
            raw = r.stdout.strip()
            callback(clean_mermaid(raw), None)
        except FileNotFoundError:
            # CLI disappeared — retry via API key
            _call_via_api(prompt, callback)
        except subprocess.TimeoutExpired:
            callback(None, "Timed out waiting for claude CLI (60 s)")
        except Exception as e:
            callback(None, f"CLI error: {str(e)[:120]}")
    threading.Thread(target=_work, daemon=True).start()

# ── API-key path: for distribution / selling ──────────────────────────────────
def _call_via_api(prompt: str, callback):
    """Fire-and-forget thread — direct Anthropic API (requires key)."""
    def _work():
        api_key = load_api_key()
        if not api_key:
            callback(None, "No API key — click the key icon to add one.")
            return
        try:
            body = json.dumps({
                "model": load_model(),
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                raw = data["content"][0]["text"].strip()
                callback(clean_mermaid(raw), None)
        except urllib.error.HTTPError as e:
            try:
                body_text = e.read().decode()[:120]
            except:
                body_text = ""
            callback(None, f"HTTP {e.code}: {body_text}")
        except Exception as e:
            callback(None, f"API error: {str(e)[:100]}")
    threading.Thread(target=_work, daemon=True).start()

# ── Unified entry point ────────────────────────────────────────────────────────
def ask_claude(prompt: str, callback):
    """CLI first (Max sub, free), API key as fallback."""
    if _check_cli():
        _call_via_cli(prompt, callback)
    else:
        _call_via_api(prompt, callback)

# ── API key dialog ─────────────────────────────────────────────────────────────
def show_api_key_dialog(parent, on_save):
    dlg = tk.Toplevel(parent)
    dlg.title("API Key")
    dlg.configure(bg=BG2)
    dlg.resizable(False, False)
    dlg.grab_set()

    # Center on parent
    parent.update_idletasks()
    px = parent.winfo_x() + parent.winfo_width() // 2
    py = parent.winfo_y() + parent.winfo_height() // 2
    dlg.geometry(f"380x160+{px - 190}+{py - 80}")

    tk.Label(dlg, text="Anthropic API Key", font=("Consolas", 10, "bold"),
             fg=BLUE, bg=BG2).pack(pady=(18, 4))
    tk.Label(dlg, text="Optional — only needed if distributing without Claude Code",
             font=("Consolas", 8), fg=FG_DIM, bg=BG2).pack()

    entry_frame = tk.Frame(dlg, bg=BG2, padx=16, pady=10)
    entry_frame.pack(fill="x")
    entry = tk.Entry(entry_frame, font=("Consolas", 9), bg=BG3, fg=FG,
                     insertbackground=BLUE, relief="flat",
                     highlightthickness=1, highlightbackground=BG3,
                     highlightcolor=BLUE, show="*")
    entry.pack(fill="x", ipady=5)
    entry.focus_set()

    btn_row = tk.Frame(dlg, bg=BG2, padx=16)
    btn_row.pack(fill="x")

    def _save():
        key = entry.get().strip()
        if key:
            save_api_key(key)
            on_save()
            dlg.destroy()
        else:
            entry.config(highlightbackground=RED)

    def _cancel():
        dlg.destroy()

    tk.Button(btn_row, text="Save", font=("Consolas", 9, "bold"),
              fg=BG, bg=GREEN, relief="flat", padx=18, pady=4,
              cursor="hand2", command=_save).pack(side="right", padx=(4, 0))
    tk.Button(btn_row, text="Cancel", font=("Consolas", 9),
              fg=FG_DIM, bg=BG3, relief="flat", padx=12, pady=4,
              cursor="hand2", command=_cancel).pack(side="right")

    entry.bind("<Return>", lambda e: _save())
    entry.bind("<Escape>", lambda e: _cancel())

# ── Chromium app-mode launcher ────────────────────────────────────────────────
_CHROMIUM_EXE = ""

def _find_chromium_for_app() -> str:
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

def _get_chromium() -> str:
    global _CHROMIUM_EXE
    if not _CHROMIUM_EXE:
        _CHROMIUM_EXE = _find_chromium_for_app()
    return _CHROMIUM_EXE

# ── Diagram HTML generator ────────────────────────────────────────────────────
def _make_diagram_html(mermaid_code: str) -> str:  # noqa: C901
    # Escape for JS template literal
    js_code = (mermaid_code
               .replace("\\", "\\\\")
               .replace("`", "\\`")
               .replace("$", "\\$"))
    ver = __version__

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MermaidBot v{ver} — Diagram</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--bg4:#30363d;
  --fg:#e6edf3;--dim:#6e7681;--dim2:#484f58;
  --blue:#79c0ff;--green:#7ee787;--yellow:#e3b341;
  --red:#ff7b72;--teal:#76e3ea;--purple:#d2a8ff;
}}
html,body{{height:100%;overflow:hidden;background:var(--bg);color:var(--fg);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px}}

/* ── Toolbar ── */
#toolbar{{
  -webkit-app-region:drag;
  height:40px;background:var(--bg2);
  border-bottom:1px solid var(--bg3);
  display:flex;align-items:center;gap:4px;padding:0 8px;
  user-select:none;z-index:100;position:relative;
}}
#toolbar *{{-webkit-app-region:no-drag}}
.tb-brand{{color:var(--teal);font-weight:700;font-size:13px;letter-spacing:.04em}}
.tb-ver{{color:var(--dim2);font-size:10px;margin-right:2px}}
.sep{{width:1px;height:22px;background:var(--bg3);margin:0 4px;flex-shrink:0}}
.tb-spacer{{flex:1;-webkit-app-region:drag}}

/* buttons */
.btn{{
  background:none;border:none;color:var(--dim);cursor:pointer;
  padding:3px 7px;border-radius:5px;font-size:12px;line-height:1;
  transition:color .12s,background .12s;white-space:nowrap;
}}
.btn:hover{{color:var(--fg);background:var(--bg3)}}
.btn.active{{color:var(--blue)}}
.btn.danger:hover{{color:var(--red);background:#2d1117}}
.btn.ok:hover{{color:var(--green)}}
.btn.warn:hover{{color:var(--yellow)}}
select.tb-sel{{
  background:var(--bg3);color:var(--fg);border:1px solid var(--bg4);
  border-radius:5px;padding:2px 6px;font-size:11px;cursor:pointer;
  outline:none;
}}
select.tb-sel:hover{{border-color:var(--blue)}}
#anim-ctr{{color:var(--dim2);font-size:10px;min-width:36px;text-align:center}}

/* ── Diagram area ── */
#diagram-area{{
  width:100%;height:calc(100vh - 62px);overflow:hidden;
  position:relative;background:var(--bg);
}}
#pz-wrap{{
  width:100%;height:100%;
  display:flex;align-items:center;justify-content:center;
  cursor:grab;
}}
#pz-wrap:active{{cursor:grabbing}}
#pz-inner{{transform-origin:0 0;will-change:transform}}

/* mermaid SVG overrides */
.mermaid svg{{max-width:none!important;font-family:inherit}}
.mermaid .node rect,.mermaid .node circle,.mermaid .node polygon,
.mermaid .node ellipse,.mermaid .node path{{cursor:pointer}}
.mm-node-hover rect,.mm-node-hover circle,.mm-node-hover polygon{{
  filter:brightness(1.35);
}}

/* ── Animations ── */
.mm-anim-hidden{{opacity:0;transition:opacity .45s ease}}
.mm-anim-visible{{opacity:1;transition:opacity .45s ease}}

@keyframes mm-pulse{{
  0%,100%{{filter:drop-shadow(0 0 3px var(--blue)) drop-shadow(0 0 0px transparent)}}
  50%{{filter:drop-shadow(0 0 10px var(--blue)) drop-shadow(0 0 18px #79c0ff55)}}
}}
.mm-key-node{{animation:mm-pulse 1.8s ease-in-out infinite}}

@keyframes mm-outline-pulse{{
  0%,100%{{stroke:var(--blue);stroke-width:2;opacity:.9}}
  50%{{stroke:var(--blue);stroke-width:5;opacity:.5}}
}}

/* ── Status bar ── */
#statusbar{{
  position:fixed;bottom:0;left:0;right:0;height:22px;
  background:var(--bg2);border-top:1px solid var(--bg3);
  display:flex;align-items:center;padding:0 10px;gap:16px;
  font-size:10px;color:var(--dim2);z-index:100;
}}
#sb-status{{color:var(--dim)}}
#sb-hint{{margin-left:auto;color:var(--dim2)}}

/* ── Node tooltip ── */
#tooltip{{
  position:fixed;bottom:26px;left:10px;
  background:var(--bg3);border:1px solid var(--bg4);
  border-radius:6px;padding:4px 10px;font-size:11px;
  color:var(--teal);pointer-events:none;
  opacity:0;transition:opacity .15s;z-index:200;
}}
#tooltip.show{{opacity:1}}

/* ── Edit panel ── */
#edit-panel{{
  position:fixed;bottom:22px;left:0;right:0;z-index:91;
  background:var(--bg2);border-top:1px solid var(--bg3);
  transform:translateY(100%);transition:transform .25s ease;
  padding:8px 12px 10px;
}}
#edit-panel.open{{transform:translateY(0)}}
.edit-panel-header{{display:flex;align-items:center;gap:8px;margin-bottom:6px}}
.edit-panel-title{{font-size:12px;font-weight:600;color:var(--teal);flex:1}}
#edit-code{{
  width:100%;height:130px;
  background:#0d1f0f;color:var(--green);
  border:1px solid var(--bg4);border-radius:5px;
  font-family:Consolas,monospace;font-size:12px;
  padding:6px 8px;resize:vertical;outline:none;line-height:1.5;
}}
#edit-code:focus{{border-color:var(--blue)}}
#edit-toast{{font-size:10px;color:var(--dim);margin-top:4px;min-height:14px;transition:opacity .3s}}

/* ── Ask Claude panel ── */
#ask-panel{{
  position:fixed;bottom:22px;left:0;right:0;z-index:90;
  background:rgba(13,17,23,.97);border-top:1px solid rgba(121,192,255,.25);
  display:flex;align-items:center;gap:8px;padding:7px 14px;
  transform:translateY(100%);transition:transform .25s ease;
}}
#ask-panel.open{{transform:translateY(0)}}
.ask-lbl{{font-size:10px;color:var(--teal);font-weight:700;white-space:nowrap;letter-spacing:.04em}}
#ask-input{{
  flex:1;background:var(--bg3);color:var(--fg);
  border:1px solid var(--bg4);border-radius:6px;
  padding:5px 10px;font-size:12px;font-family:inherit;outline:none;
}}
#ask-input:focus{{border-color:var(--blue)}}
#ask-input::placeholder{{color:var(--dim2)}}
#ask-btn{{
  background:var(--blue);color:var(--bg);border:none;
  border-radius:6px;padding:5px 14px;font-size:12px;font-weight:700;
  cursor:pointer;white-space:nowrap;transition:opacity .15s;
}}
#ask-btn:hover{{opacity:.85}}
#ask-btn:disabled{{background:var(--bg4);color:var(--dim);cursor:default}}
#ask-status{{font-size:10px;color:var(--dim);min-width:80px}}
</style>
</head>
<body>

<div id="toolbar">
  <span class="tb-brand">MM</span>
  <span class="tb-ver">v{__version__}</span>
  <div class="sep"></div>

  <select class="tb-sel" id="font-sel" title="Font" onchange="changeFont(this.value)">
    <option value="'Segoe UI',system-ui">Segoe UI</option>
    <option value="Consolas,monospace">Consolas</option>
    <option value="Georgia,serif">Georgia</option>
    <option value="'Arial',sans-serif">Arial</option>
    <option value="'Trebuchet MS',sans-serif">Trebuchet</option>
  </select>

  <select class="tb-sel" id="theme-sel" title="Theme" onchange="changeTheme(this.value)">
    <option value="dark">Dark</option>
    <option value="default">Light</option>
    <option value="forest">Forest</option>
    <option value="neutral">Neutral</option>
    <option value="base">Base</option>
  </select>

  <div class="sep"></div>

  <button class="btn" title="First"       onclick="animFirst()">⏮</button>
  <button class="btn" title="Step back"   onclick="animBack()">⏪</button>
  <button class="btn" id="btn-play" title="Play / Pause" onclick="animToggle()">▶</button>
  <button class="btn" title="Step fwd"    onclick="animFwd()">⏩</button>
  <button class="btn" title="Last"        onclick="animLast()">⏭</button>
  <button class="btn" id="btn-loop" title="Loop" onclick="toggleLoop()">🔁</button>
  <button class="btn" title="Replay"      onclick="animReplay()">↺</button>
  <span id="anim-ctr">—/—</span>

  <div class="sep"></div>

  <button class="btn ok"   title="Save PNG"      onclick="savePng()">💾 PNG</button>
  <button class="btn"      title="Copy SVG+JS"   onclick="copySvgJs()">⟨/⟩ SVG</button>
  <button class="btn"      title="Copy code"     onclick="copyCode()">📋 Code</button>
  <div class="sep"></div>
  <button class="btn"      title="Edit diagram code" onclick="toggleEditPanel()">✏ Edit</button>
  <button class="btn" style="color:var(--teal);font-weight:700" title="Ask Claude to modify diagram" onclick="toggleAskPanel()">✦ Ask Claude</button>

  <div class="tb-spacer"></div>

  <button class="btn warn" title="Minimise" onclick="window.close()">−</button>
  <button class="btn ok"   id="btn-max" title="Maximise" onclick="toggleMax()">□</button>
  <button class="btn danger" title="Close" onclick="window.close()">×</button>
</div>

<div id="diagram-area">
  <div id="pz-wrap">
    <div id="pz-inner">
      <div class="mermaid" id="mm-root"></div>
    </div>
  </div>
</div>

<div id="statusbar">
  <span id="sb-status">Rendering…</span>
  <span id="sb-hint">Scroll = zoom · Drag = pan · Dbl-click = reset · Click node = info</span>
</div>
<div id="tooltip"></div>

<!-- ✏ Edit panel — slides up from bottom -->
<div id="edit-panel">
  <div class="edit-panel-header">
    <span class="edit-panel-title">✏ Edit Diagram Code</span>
    <button class="btn ok" onclick="regenDiagram()" title="Re-render from this code">↺ Regen</button>
    <button class="btn"    onclick="copyEditCode()" title="Copy to clipboard">📋</button>
    <button class="btn"    onclick="toggleEditPanel()" title="Close panel">▾ Close</button>
  </div>
  <textarea id="edit-code" spellcheck="false">{js_code}</textarea>
  <div id="edit-toast"></div>
</div>

<!-- ✦ Ask Claude panel — slides up from bottom -->
<div id="ask-panel">
  <span class="ask-lbl">✦ Ask Claude</span>
  <input id="ask-input" type="text"
    placeholder="e.g. add error handling, show caching layer, highlight the bottleneck…" />
  <button id="ask-btn" onclick="sendAskClaude()">Redraw →</button>
  <span id="ask-status"></span>
</div>

<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
// ════════════════════════════════════════════════════════════════════════
//  MermaidBot Diagram Player  v{__version__}
//  Namespace: mmDiagram  |  All nodes: data-mm-node-id, .mm-node
// ════════════════════════════════════════════════════════════════════════
const MM_VERSION  = "{__version__}";
const MM_NS       = "mmDiagram";
const MM_SOURCE   = `{js_code}`;

// ── Export data object (populated after render) ───────────────────────
const mmDiagram = {{
  version : MM_VERSION,
  ns      : MM_NS,
  source  : MM_SOURCE,
  nodes   : [],
  edges   : [],
  get svg(){{ return document.querySelector('#mm-root svg')?.outerHTML || '' }},
}};

// ── Mermaid init ──────────────────────────────────────────────────────
let _theme = 'dark';
let _font  = "'Segoe UI',system-ui";

function mmConfig(theme){{
  return {{
    startOnLoad: false, theme,
    themeVariables:{{
      background:'#0d1117', primaryColor:'#21262d',
      primaryTextColor:'#e6edf3', primaryBorderColor:'#79c0ff',
      lineColor:'#76e3ea', secondaryColor:'#161b22',
      tertiaryColor:'#161b22', edgeLabelBackground:'#21262d',
      fontFamily:_font, fontSize:'14px',
    }},
    securityLevel:'loose',
    flowchart:{{ curve:'basis', useMaxWidth:false }},
  }};
}}

async function renderDiagram(theme){{
  _theme = theme || _theme;
  mermaid.initialize(mmConfig(_theme));
  const el = document.getElementById('mm-root');
  el.innerHTML = '';
  try{{
    const uid = MM_NS + '_' + Date.now();
    const {{svg}} = await mermaid.render(uid, MM_SOURCE);
    el.innerHTML = svg;
    postProcess(el);
    buildAnimSeq();
    showAll();  // start fully visible; animation is opt-in
    status('Ready  ·  v{__version__}');
  }} catch(e){{
    el.innerHTML = `<div style="color:#ff7b72;padding:24px;font-family:monospace">
      ⚠ Render error:<br><pre>${{e.message}}</pre></div>`;
    status('Render error — check code', true);
  }}
}}

// ── SVG post-processing ───────────────────────────────────────────────
function postProcess(container){{
  const svg = container.querySelector('svg');
  if(!svg) return;
  svg.setAttribute('data-mm-ns', MM_NS);
  svg.removeAttribute('height'); // let CSS size it

  // Nodes
  const nodes = [...svg.querySelectorAll('.node')];
  nodes.forEach((n,i)=>{{
    const nid = MM_NS+'_node_'+i;
    n.classList.add('mm-node');
    n.setAttribute('data-mm-node-id', nid);
    n.setAttribute('data-mm-index', i);
    n.style.cursor = 'pointer';
    const label = (n.querySelector('.label,text,.nodeLabel')
                    ||n).textContent.trim().replace(/\\s+/g,' ');
    mmDiagram.nodes.push({{id:nid, index:i, label}});
    n.addEventListener('click',   ()=> onNodeClick(n, i));
    n.addEventListener('mouseenter',()=> onNodeHover(n,true));
    n.addEventListener('mouseleave',()=> onNodeHover(n,false));
  }});

  // Edges
  const edges = [...svg.querySelectorAll('.edgePath,.edge')];
  edges.forEach((e,i)=>{{
    const eid = MM_NS+'_edge_'+i;
    e.classList.add('mm-edge');
    e.setAttribute('data-mm-edge-id', eid);
    mmDiagram.edges.push({{id:eid, index:i}});
  }});

  // Mark terminal node (key node) — last node with no outgoing SVG arrow
  markKeyNode(nodes);
}}

function markKeyNode(nodes){{
  if(!nodes.length) return;
  // Parse source to find which node IDs have no outgoing edges
  const src = MM_SOURCE;
  const outgoing = new Set();
  const allIds   = new Set();
  src.split('\\n').forEach(line=>{{
    const m = line.match(/([\\w]+)(?:\\[[^\\]]*\\]|\\([^)]*\\))?\\s*-+>+(?:\\|[^|]*\\|)?\\s*([\\w]+)/);
    if(m){{ outgoing.add(m[1]); allIds.add(m[1]); allIds.add(m[2]); }}
  }});
  const terminals = [...allIds].filter(id=>!outgoing.has(id));
  // Find matching SVG node
  let keyNode = nodes[nodes.length-1]; // fallback: last node
  if(terminals.length){{
    for(const n of [...nodes].reverse()){{
      const lbl = (n.querySelector('.label,text,.nodeLabel')||n).textContent.trim().toLowerCase();
      if(terminals.some(t=>lbl.includes(t.toLowerCase()))){{ keyNode=n; break; }}
    }}
  }}
  keyNode.classList.add('mm-key-node');
  keyNode.setAttribute('data-mm-key','true');
  const rect = keyNode.querySelector('rect,circle,polygon,ellipse');
  if(rect){{
    rect.style.animation='mm-outline-pulse 1.8s ease-in-out infinite';
  }}
}}

// ── Node interaction ──────────────────────────────────────────────────
function onNodeClick(node, i){{
  const info = mmDiagram.nodes[i] || {{}};
  tooltip(`Node ${{i+1}}: ${{info.label||'?'}}`);
  status(`Clicked: ${{info.label||'node '+i}}`);
}}
function onNodeHover(node, enter){{
  node.style.filter = enter ? 'brightness(1.3)' : '';
}}
function tooltip(msg){{
  const t = document.getElementById('tooltip');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._tid);
  t._tid = setTimeout(()=>t.classList.remove('show'), 3000);
}}

// ── Animation ─────────────────────────────────────────────────────────
let _seq = [];          // interleaved [node, edge, node, edge …]
let _step = -1;
let _playing = false;
let _loop = false;
let _timer = null;
const STEP_MS = 550;

function buildAnimSeq(){{
  const svg = document.querySelector('#mm-root svg');
  if(!svg) return;
  const nodes = [...svg.querySelectorAll('.mm-node')];
  const edges = [...svg.querySelectorAll('.mm-edge')];
  _seq = [];
  const max = Math.max(nodes.length, edges.length);
  for(let i=0;i<max;i++){{
    if(nodes[i]) _seq.push(nodes[i]);
    if(edges[i]) _seq.push(edges[i]);
  }}
  _step = _seq.length-1;
  // all visible to start
  _seq.forEach(el=>{{ el.classList.remove('mm-anim-hidden'); el.classList.add('mm-anim-visible'); }});
  stepDisplay();
}}

function applyStep(n){{
  _seq.forEach((el,i)=>{{
    if(i<=n){{ el.classList.remove('mm-anim-hidden'); el.classList.add('mm-anim-visible'); }}
    else{{     el.classList.remove('mm-anim-visible'); el.classList.add('mm-anim-hidden'); }}
  }});
  _step=n; stepDisplay();
}}
function showAll(){{
  _seq.forEach(el=>{{ el.classList.remove('mm-anim-hidden'); el.classList.add('mm-anim-visible'); }});
  _step=_seq.length-1; stepDisplay();
}}
function hideAll(){{
  _seq.forEach(el=>{{ el.classList.remove('mm-anim-visible'); el.classList.add('mm-anim-hidden'); }});
  _step=-1; stepDisplay();
}}
function stepDisplay(){{
  document.getElementById('anim-ctr').textContent =
    _seq.length ? `${{Math.max(0,_step+1)}}/${{_seq.length}}` : '—/—';
}}
function animFirst(){{ stopPlay(); hideAll(); }}
function animBack() {{ stopPlay(); if(_step>-1) applyStep(_step-1); }}
function animFwd()  {{ stopPlay(); if(_step<_seq.length-1) applyStep(_step+1); }}
function animLast() {{ stopPlay(); showAll(); }}
function animReplay(){{ stopPlay(); hideAll(); setTimeout(startPlay,80); }}
function toggleLoop(){{
  _loop=!_loop;
  document.getElementById('btn-loop').classList.toggle('active',_loop);
}}
function animToggle(){{ _playing ? stopPlay() : startPlay(); }}
function startPlay(){{
  if(_step>=_seq.length-1){{ hideAll(); }}
  _playing=true;
  document.getElementById('btn-play').textContent='⏸';
  document.getElementById('btn-play').classList.add('active');
  _timer=setInterval(()=>{{
    if(_step<_seq.length-1){{ applyStep(_step+1); }}
    else if(_loop){{ hideAll(); }}
    else{{ stopPlay(); }}
  }},STEP_MS);
}}
function stopPlay(){{
  _playing=false;
  document.getElementById('btn-play').textContent='▶';
  document.getElementById('btn-play').classList.remove('active');
  if(_timer){{ clearInterval(_timer); _timer=null; }}
}}

// ── Pan / Zoom ────────────────────────────────────────────────────────
let _scale=1, _px=0, _py=0, _dragging=false, _lx=0, _ly=0;

function applyXform(){{
  document.getElementById('pz-inner').style.transform=
    `translate(${{_px}}px,${{_py}}px) scale(${{_scale}})`;
}}
function initPanZoom(){{
  const wrap = document.getElementById('pz-wrap');
  wrap.addEventListener('wheel',e=>{{
    e.preventDefault();
    const rect = wrap.getBoundingClientRect();
    const mx = e.clientX-rect.left, my=e.clientY-rect.top;
    const d = e.deltaY>0 ? 0.88 : 1.14;
    const ns = Math.min(8,Math.max(0.15,_scale*d));
    _px = mx - (mx-_px)*(ns/_scale);
    _py = my - (my-_py)*(ns/_scale);
    _scale=ns; applyXform();
  }},{{passive:false}});
  wrap.addEventListener('mousedown',e=>{{
    if(e.target.closest('.mm-node,button,select')) return;
    _dragging=true; _lx=e.clientX; _ly=e.clientY;
  }});
  document.addEventListener('mousemove',e=>{{
    if(!_dragging) return;
    _px+=e.clientX-_lx; _py+=e.clientY-_ly;
    _lx=e.clientX; _ly=e.clientY; applyXform();
  }});
  document.addEventListener('mouseup',()=>{{ _dragging=false; }});
  wrap.addEventListener('dblclick',e=>{{
    if(e.target.closest('.mm-node,button,select')) return;
    _scale=1;_px=0;_py=0; applyXform();
  }});
}}

// ── Font / Theme ──────────────────────────────────────────────────────
function changeFont(f){{
  _font=f;
  document.getElementById('pz-inner').style.fontFamily=f;
  document.querySelectorAll('#mm-root svg text,.label,.nodeLabel').forEach(el=>el.style.fontFamily=f);
}}
async function changeTheme(t){{ await renderDiagram(t); }}

// ── Maximise / Fullscreen ─────────────────────────────────────────────
function toggleMax(){{
  if(!document.fullscreenElement){{
    document.documentElement.requestFullscreen().catch(()=>{{
      window.resizeTo(screen.width,screen.height); window.moveTo(0,0);
    }});
    document.getElementById('btn-max').textContent='❐';
  }} else {{
    document.exitFullscreen();
    document.getElementById('btn-max').textContent='□';
  }}
}}

// ── Save PNG ──────────────────────────────────────────────────────────
function savePng(){{
  const svg=document.querySelector('#mm-root svg');
  if(!svg)return;
  const clone=svg.cloneNode(true);
  const bb=svg.getBoundingClientRect();
  const w=Math.max(bb.width*2,800), h=Math.max(bb.height*2,400);
  clone.setAttribute('width',w); clone.setAttribute('height',h);
  const blob=new Blob([new XMLSerializer().serializeToString(clone)],
                      {{type:'image/svg+xml'}});
  const url=URL.createObjectURL(blob);
  const canvas=document.createElement('canvas');
  canvas.width=w; canvas.height=h;
  const ctx=canvas.getContext('2d');
  ctx.fillStyle='#0d1117'; ctx.fillRect(0,0,w,h);
  const img=new Image();
  img.onload=()=>{{
    ctx.drawImage(img,0,0,w,h); URL.revokeObjectURL(url);
    const a=document.createElement('a');
    a.download=`mermaid_${{Date.now()}}.png`;
    a.href=canvas.toDataURL('image/png'); a.click();
    status('PNG saved!');
  }};
  img.src=url;
}}

// ── Copy SVG + JS wrapper ─────────────────────────────────────────────
function copySvgJs(){{
  const svg=document.querySelector('#mm-root svg');
  if(!svg)return;
  const svgStr=svg.outerHTML.replace(/`/g,'\\`');
  const out=`// ═══════════════════════════════════════════════
// MermaidBot Diagram Export — v${{MM_VERSION}}
// Generated: ${{new Date().toISOString()}}
// Namespace: ${{MM_NS}}
// ═══════════════════════════════════════════════
const ${{MM_NS}} = {{
  version : "${{MM_VERSION}}",
  source  : \`${{MM_SOURCE.replace(/`/g,'\\`')}}\`,
  nodes   : ${{JSON.stringify(mmDiagram.nodes,null,2)}},
  edges   : ${{JSON.stringify(mmDiagram.edges,null,2)}},
  svg     : \`${{svgStr}}\`,
  /** Inject into any DOM: document.getElementById('container').innerHTML = ${{MM_NS}}.svg */
}};`;
  navigator.clipboard.writeText(out)
    .then(()=>status('SVG + JS wrapper copied!'));
}}

function copyCode(){{
  navigator.clipboard.writeText(MM_SOURCE)
    .then(()=>status('Mermaid code copied!'));
}}

// ── Status helper ─────────────────────────────────────────────────────
function status(msg,err){{
  const el=document.getElementById('sb-status');
  el.textContent=msg; el.style.color=err?'#ff7b72':'#6e7681';
}}

// ── Edit panel ───────────────────────────────────────────────────────
function toggleEditPanel(){{
  const p = document.getElementById('edit-panel');
  const open = p.classList.toggle('open');
  if(open){{
    document.getElementById('ask-panel').classList.remove('open');
    const ta = document.getElementById('edit-code');
    if(!ta.value.trim()) ta.value = MM_SOURCE;
    ta.focus();
  }}
  status(open ? 'Edit panel open — change the code, then click ↺ Regen' : 'Ready');
}}

async function regenDiagram(){{
  const src = document.getElementById('edit-code').value.trim();
  if(!src) return;
  mermaid.initialize(mmConfig(_theme));
  const el = document.getElementById('mm-root');
  el.innerHTML = '';
  try{{
    const uid = MM_NS + '_regen_' + Date.now();
    const {{svg}} = await mermaid.render(uid, src);
    el.innerHTML = svg;
    postProcess(el);
    buildAnimSeq();
    showAll();
    showEditToast('✓ Diagram updated!');
    status('Re-rendered');
  }} catch(e) {{
    showEditToast('⚠ ' + e.message);
    status('Render error', true);
  }}
}}

function copyEditCode(){{
  const src = document.getElementById('edit-code').value;
  navigator.clipboard.writeText(src).then(()=>showEditToast('Copied!'));
}}

function showEditToast(msg){{
  const t = document.getElementById('edit-toast');
  t.textContent = msg; t.style.opacity = '1';
  clearTimeout(t._tid);
  t._tid = setTimeout(()=>{{ t.style.opacity='0'; }}, 3500);
}}

// ── Ask Claude ────────────────────────────────────────────────────────
function toggleAskPanel(){{
  const p = document.getElementById('ask-panel');
  const open = p.classList.toggle('open');
  if(open){{
    document.getElementById('edit-panel').classList.remove('open');
    document.getElementById('ask-input').focus();
  }}
  status(open ? '✦ Ask Claude — describe your changes, press Enter or click Redraw' : 'Ready');
}}

let _askBusy = false;

async function sendAskClaude(){{
  if(_askBusy) return;
  const inp = document.getElementById('ask-input');
  const prompt = inp.value.trim();
  if(!prompt) return;
  _askBusy = true;
  const btn = document.getElementById('ask-btn');
  const st  = document.getElementById('ask-status');
  btn.disabled = true; btn.textContent = '…';
  st.textContent = 'Asking Claude…'; st.style.color = 'var(--yellow)';

  const currentSrc = (document.getElementById('edit-code')?.value?.trim()) || MM_SOURCE;

  try{{
    const resp = await fetch('/api', {{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{action:'diagram', prompt, source:currentSrc}})
    }});
    if(!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    if(data.error) throw new Error(data.error);
    if(data.code){{
      const ta = document.getElementById('edit-code');
      if(ta) ta.value = data.code;
      await regenFromCode(data.code);
      inp.value = '';
      st.textContent = '✓ Done!'; st.style.color = 'var(--green)';
    }}
  }} catch(e) {{
    // No server (file:// mode) — fall back to edit panel with help message
    st.textContent = 'No AI server — use ✏ Edit'; st.style.color = 'var(--yellow)';
    setTimeout(()=>{{
      document.getElementById('ask-panel').classList.remove('open');
      toggleEditPanel();
    }}, 1200);
  }}

  btn.disabled = false; btn.textContent = 'Redraw →';
  _askBusy = false;
  setTimeout(()=>{{ st.textContent = ''; }}, 5000);
}}

async function regenFromCode(src){{
  mermaid.initialize(mmConfig(_theme));
  const el = document.getElementById('mm-root');
  el.innerHTML = '';
  try{{
    const uid = MM_NS + '_ask_' + Date.now();
    const {{svg}} = await mermaid.render(uid, src);
    el.innerHTML = svg;
    postProcess(el);
    buildAnimSeq();
    showAll();
    status('Diagram redrawn by Claude  ✦');
  }} catch(e) {{
    status('Render error: ' + e.message, true);
  }}
}}

// Escape closes any open panel
document.addEventListener('keydown', e=>{{
  if(e.key === 'Escape'){{
    document.getElementById('edit-panel').classList.remove('open');
    document.getElementById('ask-panel').classList.remove('open');
  }}
  if(e.key === 'Enter' && document.getElementById('ask-panel').classList.contains('open')){{
    e.preventDefault();
    sendAskClaude();
  }}
}});

// ── Boot ──────────────────────────────────────────────────────────────
initPanZoom();
renderDiagram('dark');
</script>
</body>
</html>"""


# ── Floating diagram popup — launches Chromium app-mode window ────────────────
class DiagramPopup:
    def __init__(self, _master, mermaid_code: str, _photo_refs=None):
        html = _make_diagram_html(mermaid_code)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False,
            prefix="mmbot_", encoding="utf-8"
        )
        tmp.write(html)
        tmp.close()
        self._path = tmp.name
        threading.Thread(target=self._launch, daemon=True).start()

    def _launch(self):
        exe = _get_chromium()
        url = "file:///" + self._path.replace("\\", "/")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        if exe:
            subprocess.Popen(
                [exe, f"--app={url}", "--window-size=960,620",
                 "--window-position=120,80"],
                creationflags=flags,
            )
        else:
            webbrowser.open(url)


# ── Main App — 200×100 compact widget ──────────────────────────────────────────
class MermaidBot:
    W, H = 200, 100

    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)
        self.root.configure(bg=BG)
        self.root.geometry(f"{self.W}x{self.H}+80+80")
        self.root.resizable(False, False)

        self.history = load_history()
        self._busy = False
        self._photo_refs: list = []
        self._drag_ox = self._drag_oy = 0

        self._build()
        self.root.after(200, self._keep_top)

        if not _check_cli() and not load_api_key():
            self.root.after(600, self._prompt_api_key)

    # ── Layout ─────────────────────────────────────────────────────────────────
    def _build(self):
        outer = tk.Frame(self.root, bg=BG,
                         highlightthickness=1, highlightbackground=BG3)
        outer.pack(fill="both", expand=True)

        # ── Drag / title bar ──────────────────────────────────────────────────
        bar = tk.Frame(outer, bg=BG2, height=22)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="MM",
                 font=("Consolas", 8, "bold"),
                 fg=TEAL, bg=BG2).pack(side="left", padx=(6, 2))

        mode_col = TEAL if _check_cli() else YELLOW
        mode_txt = "CC✓" if _check_cli() else "key"
        tk.Label(bar, text=mode_txt,
                 font=("Consolas", 7), fg=mode_col, bg=BG2).pack(side="left")

        # Window controls (right-side)
        for txt, col, cmd in [
            ("×", RED,    self._hide_window),
            ("□", FG_DIM, self._toggle_size),
            ("−", YELLOW, self._hide_window),
        ]:
            b = tk.Label(bar, text=txt, font=("Consolas", 10, "bold"),
                         fg=FG_DIM, bg=BG2, cursor="hand2", width=2)
            b.pack(side="right")
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>",    lambda e, w=b, c=col: w.config(fg=c))
            b.bind("<Leave>",    lambda e, w=b: w.config(fg=FG_DIM))

        # Drag
        bar.bind("<ButtonPress-1>",  self._drag_start)
        bar.bind("<B1-Motion>",      self._drag_move)

        # ── Input row ─────────────────────────────────────────────────────────
        mid = tk.Frame(outer, bg=BG, pady=4, padx=4)
        mid.pack(fill="both", expand=True)

        self.entry = tk.Entry(
            mid, font=("Consolas", 9),
            bg=BG3, fg=FG_DIM,
            insertbackground=BLUE,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BG3,
            highlightcolor=BLUE,
        )
        self.entry.pack(side="left", fill="both", expand=True, ipady=6)
        self.entry.bind("<Return>",   self._on_send)
        self.entry.bind("<FocusIn>",  self._clear_placeholder)
        self.entry.bind("<FocusOut>", self._restore_placeholder)

        self._send_btn = tk.Button(
            mid, text="→",
            font=("Consolas", 12, "bold"),
            fg=BG, bg=TEAL, relief="flat",
            padx=8, cursor="hand2",
            command=lambda: self._on_send(None),
        )
        self._send_btn.pack(side="right", padx=(4, 0), fill="y")

        # ── Status strip ──────────────────────────────────────────────────────
        self._status_lbl = tk.Label(
            outer, text="ready · type and hit enter",
            font=("Consolas", 7), fg=FG_DIM, bg=BG2, pady=2,
        )
        self._status_lbl.pack(fill="x", side="bottom")
        self._status_lbl.bind("<Button-3>", self._show_menu)

        self._show_placeholder()

    # ── Placeholder ────────────────────────────────────────────────────────────
    def _show_placeholder(self):
        self._placeholder_active = True
        self.entry.config(fg=FG_DIM)
        self.entry.delete(0, "end")
        self.entry.insert(0, "describe a diagram…")

    def _clear_placeholder(self, e=None):
        if self._placeholder_active:
            self.entry.delete(0, "end")
            self.entry.config(fg=FG)
            self._placeholder_active = False

    def _restore_placeholder(self, e=None):
        if not self.entry.get().strip():
            self._show_placeholder()

    # ── Status ─────────────────────────────────────────────────────────────────
    def _set_status(self, text: str, colour: str = FG_DIM):
        self._status_lbl.config(text=text, fg=colour)

    # ── Drag ───────────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._drag_ox = e.x_root - self.root.winfo_x()
        self._drag_oy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(
            f"+{e.x_root - self._drag_ox}+{e.y_root - self._drag_oy}"
        )

    # ── Toggle size (□ button) ─────────────────────────────────────────────────
    def _toggle_size(self):
        if self.root.winfo_width() <= 210:
            self.root.geometry(f"380x120")
        else:
            self.root.geometry(f"{self.W}x{self.H}")

    # ── Always on top ──────────────────────────────────────────────────────────
    def _keep_top(self):
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
        except: pass
        self.root.after(1000, self._keep_top)

    # ── Sending ────────────────────────────────────────────────────────────────
    def _on_send(self, event):
        if self._busy or self._placeholder_active:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._show_placeholder()
        self._set_busy(True)

        def _cb(mermaid_code, error):
            self.root.after(0, lambda: self._on_response(text, mermaid_code, error))

        ask_claude(text, _cb)

    def _set_busy(self, busy: bool):
        self._busy = busy
        if busy:
            self._send_btn.config(text="…", state="disabled", bg=BG3, fg=FG_DIM)
            self._set_status("thinking…", YELLOW)
        else:
            self._send_btn.config(text="→", state="normal", bg=TEAL, fg=BG)
            self._set_status("ready · type and hit enter", FG_DIM)

    # ── Response ───────────────────────────────────────────────────────────────
    def _on_response(self, prompt: str, mermaid_code, error):
        self._set_busy(False)
        if error:
            self._set_status(f"error: {error[:60]}", RED)
            return
        self._set_status("diagram ready ↗", GREEN)
        self.root.after(3000, lambda: self._set_status("ready · type and hit enter", FG_DIM))
        # Save history
        self.history.append({"prompt": prompt, "diagram": mermaid_code})
        save_history(self.history)
        # Pop out the diagram
        DiagramPopup(self.root, mermaid_code, self._photo_refs)

    # ── Right-click menu ───────────────────────────────────────────────────────
    def _show_menu(self, e=None):
        m = tk.Menu(self.root, tearoff=0, bg=BG2, fg=FG,
                    activebackground=BG3, activeforeground=FG,
                    font=("Consolas", 9), bd=0)

        # Version header (non-clickable)
        m.add_command(label=f"  MermaidBot v{__version__}", state="disabled",
                      foreground=TEAL)
        m.add_separator()

        # Mode indicator
        if _check_cli():
            m.add_command(label="✓ Claude Code (Max sub) — free",
                          state="disabled", foreground=GREEN)
        else:
            m.add_command(label="⚠  API key mode — costs money per request",
                          foreground=RED, command=self._prompt_api_key)
            # Model submenu
            sub = tk.Menu(m, tearoff=0, bg=BG2, fg=FG,
                          activebackground=BG3, font=("Consolas", 9))
            cur = load_model()
            for label, mid in MODELS:
                sub.add_command(
                    label=("✓  " if mid == cur else "    ") + label,
                    command=lambda i=mid: save_model(i)
                )
            m.add_cascade(label="    Model…", menu=sub)

        m.add_separator()
        m.add_command(label="    Set API key…",    command=self._prompt_api_key)
        m.add_command(label="    Resize compact",  command=lambda: self.root.geometry(f"{self.W}x{self.H}"))
        m.add_command(label="    Resize wide",     command=lambda: self.root.geometry("380x120"))
        m.add_separator()
        m.add_command(label="    Restart MermaidBot",
                      command=lambda: (self._quit(), selfclean.kill_and_relaunch("mermaidbot.py")))
        m.add_separator()
        m.add_command(label="    Quit", foreground=RED, command=self._quit)
        try:
            x = e.x_root if e else self.root.winfo_rootx() + 10
            y = e.y_root if e else self.root.winfo_rooty() + 80
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    # ── API key prompt ─────────────────────────────────────────────────────────
    def _prompt_api_key(self):
        def _on_save():
            self._set_status("key saved", GREEN)
            self.root.after(2000, lambda: self._set_status("ready · type and hit enter", FG_DIM))
        show_api_key_dialog(self.root, _on_save)

    # ── System tray ────────────────────────────────────────────────────────────
    def _build_tray(self):
        # Bright, distinctive icon — teal background, white "MM"
        img = PILImage.new("RGB", (64, 64), "#0d1117")
        d   = ImageDraw.Draw(img)
        # Bright teal filled circle
        d.ellipse([2, 2, 62, 62], fill="#76e3ea")
        # Dark "MM" block letters drawn manually (no font needed)
        # Left M
        for rect in [
            [10, 16, 15, 48],   # left stem
            [10, 16, 22, 22],   # top crossbar left
            [17, 22, 22, 36],   # centre-left leg
            [22, 16, 27, 36],   # centre stem
            [22, 16, 30, 22],   # top crossbar right
            [27, 22, 32, 36],   # centre-right leg
            [29, 16, 34, 48],   # right stem
        ]:
            d.rectangle(rect, fill="#0d1117")
        # Right M (offset by 18px)
        for rect in [
            [36, 16, 41, 48],
            [36, 16, 48, 22],
            [43, 22, 48, 36],
            [48, 16, 53, 36],
            [48, 16, 56, 22],
            [53, 22, 58, 36],
            [55, 16, 60, 48],
        ]:
            d.rectangle(rect, fill="#0d1117")

        menu = pystray.Menu(
            pystray.MenuItem(f"MermaidBot v{__version__}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show",    lambda: self.root.after(0, self._show_window)),
            pystray.MenuItem("Hide",    lambda: self.root.after(0, self._hide_window)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart", lambda: (
                self.root.after(0, self._quit),
                __import__('selfclean').kill_and_relaunch("mermaidbot.py")
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",    lambda: self.root.after(0, self._quit)),
        )
        self._tray = pystray.Icon("mermaidbot", img,
                                   f"MermaidBot v{__version__}", menu)
        # run_detached() is the correct call when tkinter already owns the main loop
        self._tray.run_detached()

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide_window(self):
        self.root.withdraw()

    def _quit(self):
        try: self._tray.stop()
        except: pass
        self.root.after(0, self.root.destroy)

    # ── Run ────────────────────────────────────────────────────────────────────
    def run(self):
        # X button hides to tray instead of quitting
        self.root.protocol("WM_DELETE_WINDOW", self._hide_window)
        self._build_tray()
        self.root.mainloop()


if __name__ == "__main__":
    app = MermaidBot()
    app.run()
