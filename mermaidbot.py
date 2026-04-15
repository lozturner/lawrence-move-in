"""
Lawrence: Move In — MermaidBot v1.1.0
Natural-language Mermaid diagram generator. Type anything, get a diagram.
Uses the claude CLI (Max subscription) by default — no API key needed.
Falls back to direct API key if the CLI is not available.
"""
__version__ = "1.7.0"
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

# ── Floating diagram popup ─────────────────────────────────────────────────────
class DiagramPopup:
    """Borderless, draggable floating window that shows the rendered diagram."""

    def __init__(self, master, mermaid_code: str, photo_refs: list):
        self._code = mermaid_code
        self._photo_refs = photo_refs
        self._win = tk.Toplevel(master)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.configure(bg=BG2)
        self._win.resizable(False, False)

        # Position near bottom-left of screen
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        self._win.geometry(f"+40+{sh - 500}")

        self._drag_ox = self._drag_oy = 0
        self._build()

    def _build(self):
        # ── Title bar ─────────────────────────────────────────────────────────
        bar = tk.Frame(self._win, bg=BG3, height=22)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="  Diagram",
                 font=("Consolas", 8, "bold"),
                 fg=TEAL, bg=BG3).pack(side="left")

        # Copy code button
        cp = tk.Label(bar, text=" copy code ",
                      font=("Consolas", 7), fg=FG_DIM, bg=BG3, cursor="hand2")
        cp.pack(side="right", padx=(0, 2))
        cp.bind("<Button-1>", self._copy_code)
        cp.bind("<Enter>", lambda e: cp.config(fg=TEAL))
        cp.bind("<Leave>", lambda e: cp.config(fg=FG_DIM))

        # Close button
        xb = tk.Label(bar, text=" × ", font=("Consolas", 11, "bold"),
                      fg=FG_DIM, bg=BG3, cursor="hand2")
        xb.pack(side="right")
        xb.bind("<Button-1>", lambda e: self._win.destroy())
        xb.bind("<Enter>", lambda e: xb.config(fg=RED, bg="#2d1117"))
        xb.bind("<Leave>", lambda e: xb.config(fg=FG_DIM, bg=BG3))

        # Drag
        bar.bind("<ButtonPress-1>",   self._drag_start)
        bar.bind("<B1-Motion>",       self._drag_move)

        # ── Content: loading placeholder ──────────────────────────────────────
        self._content = tk.Frame(self._win, bg=BG2)
        self._content.pack(fill="both", expand=True)

        self._loading = tk.Label(self._content,
                                  text="\n  rendering…  \n",
                                  font=("Consolas", 9, "italic"),
                                  fg=FG_DIM, bg=BG2)
        self._loading.pack(padx=16, pady=12)

        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            encoded = base64.urlsafe_b64encode(
                self._code.encode("utf-8")
            ).decode("ascii")
            url = f"https://mermaid.ink/img/{encoded}?bgColor=161b22"
            req = urllib.request.Request(url, headers={"User-Agent": "MermaidBot/1"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            img = PILImage.open(io.BytesIO(data)).convert("RGBA")
            # Cap at 700px wide
            max_w = 700
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((max_w, int(img.height * ratio)), PILImage.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._photo_refs.append(photo)
            self._win.after(0, lambda: self._show_image(photo))
        except Exception as ex:
            self._win.after(0, lambda: self._show_error(str(ex)[:120]))

    def _show_image(self, photo):
        self._loading.destroy()
        lbl = tk.Label(self._content, image=photo, bg=BG2, cursor="fleur")
        lbl.pack(padx=0, pady=0)
        lbl.bind("<ButtonPress-1>",   self._drag_start)
        lbl.bind("<B1-Motion>",       self._drag_move)
        self._win.lift()

    def _show_error(self, msg: str):
        self._loading.config(
            text=f"\n  render failed:\n  {msg}\n",
            fg=RED
        )

    def _copy_code(self, _=None):
        self._win.clipboard_clear()
        self._win.clipboard_append(self._code)

    def _drag_start(self, e):
        self._drag_ox = e.x_root - self._win.winfo_x()
        self._drag_oy = e.y_root - self._win.winfo_y()

    def _drag_move(self, e):
        self._win.geometry(
            f"+{e.x_root - self._drag_ox}+{e.y_root - self._drag_oy}"
        )


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
        if not _check_cli():
            m.add_command(label="⚠ API key mode — costs money", foreground=RED,
                          command=self._prompt_api_key)
            m.add_separator()
            # Model submenu
            sub = tk.Menu(m, tearoff=0, bg=BG2, fg=FG,
                          activebackground=BG3, font=("Consolas", 9))
            for label, mid in MODELS:
                sub.add_command(
                    label=("✓ " if mid == load_model() else "   ") + label,
                    command=lambda i=mid: save_model(i)
                )
            m.add_cascade(label="   Model…", menu=sub)
            m.add_separator()
        m.add_command(label="   Set API key…", command=self._prompt_api_key)
        m.add_separator()
        m.add_command(label="   Quit", foreground=RED, command=self._quit)
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
            pystray.MenuItem("Show",  lambda: self.root.after(0, self._show_window)),
            pystray.MenuItem("Hide",  lambda: self.root.after(0, self._hide_window)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",  lambda: self.root.after(0, self._quit)),
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
