"""
Lawrence: Move In — MermaidBot v1.0.0
Natural-language Mermaid diagram generator. Type anything, get a diagram.
"""
__version__ = "1.0.0"
import selfclean; selfclean.ensure_single("mermaidbot.py")

import json, os, re, threading, tkinter as tk
import urllib.request, webbrowser, tempfile
from pathlib import Path
from tkinter import font as tkfont

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

# ── Config / API key ───────────────────────────────────────────────────────────
def load_api_key() -> str:
    # Try config file first
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                key = cfg.get("api_key", "").strip()
                if key:
                    return key
        except:
            pass
    # Fall back to environment variable
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()

def save_api_key(key: str):
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except:
            pass
    cfg["api_key"] = key.strip()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

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

# ── LLM call ───────────────────────────────────────────────────────────────────
def ask_claude(prompt: str, callback):
    """Background thread — calls Claude and fires callback(mermaid_code, error)."""
    def _work():
        api_key = load_api_key()
        if not api_key:
            callback(None, "No API key. Click the key icon to add one.")
            return
        try:
            body = json.dumps({
                "model": "claude-3-5-haiku-20241022",
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
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
                raw = data["content"][0]["text"].strip()
                cleaned = clean_mermaid(raw)
                callback(cleaned, None)
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode()[:120]
            except:
                pass
            callback(None, f"HTTP {e.code}: {body_text}")
        except Exception as e:
            callback(None, f"Error: {str(e)[:100]}")

    threading.Thread(target=_work, daemon=True).start()

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
    tk.Label(dlg, text="Paste your key below and click Save",
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

# ── Main App ───────────────────────────────────────────────────────────────────
class MermaidBot:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MermaidBot  v1.0.0")
        self.root.configure(bg=BG)
        self.root.geometry("520x500")
        self.root.minsize(400, 360)
        self.history = load_history()
        self._busy = False
        self._build()
        # Check API key on start
        if not load_api_key():
            self.root.after(400, self._prompt_api_key)

    # ── Layout ─────────────────────────────────────────────────────────────────
    def _build(self):
        self._build_title_bar()
        self._build_chat_area()
        self._build_input_bar()
        self._show_placeholder()

    def _build_title_bar(self):
        bar = tk.Frame(self.root, bg=BG2, height=34)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="MermaidBot  v1.0.0",
                 font=("Consolas", 11, "bold"),
                 fg=BLUE, bg=BG2).pack(side="left", padx=12, pady=6)

        self.status_lbl = tk.Label(bar, text="ready",
                                    font=("Consolas", 8),
                                    fg=FG_DIM, bg=BG2)
        self.status_lbl.pack(side="right", padx=10)

        # Key button
        tk.Button(bar, text="key", font=("Consolas", 7),
                  fg=YELLOW, bg=BG3, relief="flat", padx=6, pady=2,
                  cursor="hand2",
                  command=self._prompt_api_key).pack(side="right", padx=(0, 4), pady=5)

        # Drag support
        def _sd(e): self._dx, self._dy = e.x, e.y
        def _d(e):
            self.root.geometry(
                f"+{self.root.winfo_x() + e.x - self._dx}"
                f"+{self.root.winfo_y() + e.y - self._dy}"
            )
        bar.bind("<Button-1>", _sd)
        bar.bind("<B1-Motion>", _d)

    def _build_chat_area(self):
        # Outer frame with scrollbar
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=0, pady=0)

        # Canvas + vertical scrollbar
        self._canvas = tk.Canvas(outer, bg=BG, highlightthickness=0,
                                  bd=0, relief="flat")
        vsb = tk.Scrollbar(outer, orient="vertical",
                            command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)

        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Inner frame inside canvas — this is where bubbles go
        self._inner = tk.Frame(self._canvas, bg=BG)
        self._inner_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw"
        )

        def _on_configure(e):
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))

        def _on_canvas_resize(e):
            self._canvas.itemconfig(self._inner_id, width=e.width)

        self._inner.bind("<Configure>", _on_configure)
        self._canvas.bind("<Configure>", _on_canvas_resize)

        # Mouse wheel scroll
        def _on_wheel(e):
            self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        self._canvas.bind_all("<MouseWheel>", _on_wheel)

    def _build_input_bar(self):
        bar = tk.Frame(self.root, bg=BG2, pady=8)
        bar.pack(fill="x", padx=0)

        inner = tk.Frame(bar, bg=BG2)
        inner.pack(fill="x", padx=10)

        self.entry = tk.Entry(
            inner,
            font=("Consolas", 10),
            bg=BG3, fg=FG_DIM,
            insertbackground=BLUE,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BG3,
            highlightcolor=BLUE,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.entry.bind("<Return>", self._on_send)
        self.entry.bind("<FocusIn>", self._clear_placeholder)
        self.entry.bind("<FocusOut>", self._restore_placeholder)

        self._send_btn = tk.Button(
            inner, text="Send",
            font=("Consolas", 10, "bold"),
            fg=BG, bg=BLUE, relief="flat",
            padx=14, pady=6,
            cursor="hand2",
            command=lambda: self._on_send(None),
        )
        self._send_btn.pack(side="right", padx=(8, 0))

    # ── Placeholder ────────────────────────────────────────────────────────────
    def _show_placeholder(self):
        self._placeholder_active = True
        self.entry.config(fg=FG_DIM)
        self.entry.delete(0, "end")
        self.entry.insert(0, "Say anything naturally…")

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
        self.status_lbl.config(text=text, fg=colour)

    # ── Sending ────────────────────────────────────────────────────────────────
    def _on_send(self, event):
        if self._busy or self._placeholder_active:
            return
        text = self.entry.get().strip()
        if not text:
            return

        self.entry.delete(0, "end")
        self._show_placeholder()

        self._add_user_bubble(text)
        self._set_busy(True)
        self._add_thinking_bubble()

        def _cb(mermaid_code, error):
            self.root.after(0, lambda: self._on_response(text, mermaid_code, error))

        ask_claude(text, _cb)

    def _set_busy(self, busy: bool):
        self._busy = busy
        if busy:
            self._send_btn.config(text="…", state="disabled", bg=BG3, fg=FG_DIM)
            self._set_status("thinking…", YELLOW)
        else:
            self._send_btn.config(text="Send", state="normal", bg=BLUE, fg=BG)
            self._set_status("ready", FG_DIM)

    # ── Response handler ───────────────────────────────────────────────────────
    def _on_response(self, prompt: str, mermaid_code, error):
        self._remove_thinking_bubble()
        self._set_busy(False)

        if error:
            self._add_error_bubble(error)
            return

        self._add_code_bubble(mermaid_code)

        # Save to history
        self.history.append({"prompt": prompt, "diagram": mermaid_code})
        save_history(self.history)

    # ── Bubble builders ────────────────────────────────────────────────────────
    def _add_user_bubble(self, text: str):
        row = tk.Frame(self._inner, bg=BG, pady=6)
        row.pack(fill="x", padx=10)

        lbl_you = tk.Label(row, text="You", font=("Consolas", 7),
                            fg=FG_DIM, bg=BG)
        lbl_you.pack(side="right", anchor="ne", padx=(0, 2))

        bubble = tk.Label(
            row, text=text,
            font=("Consolas", 9),
            fg=FG, bg=BG3,
            wraplength=360,
            justify="right",
            anchor="e",
            padx=10, pady=6,
            relief="flat",
        )
        bubble.pack(side="right", anchor="e")
        self._scroll_to_bottom()

    def _add_thinking_bubble(self):
        self._thinking_frame = tk.Frame(self._inner, bg=BG, pady=6)
        self._thinking_frame.pack(fill="x", padx=10)

        tk.Label(self._thinking_frame, text="MermaidBot",
                 font=("Consolas", 7), fg=FG_DIM, bg=BG).pack(side="left", anchor="nw", padx=(0, 2))
        self._thinking_lbl = tk.Label(
            self._thinking_frame, text="generating diagram…",
            font=("Consolas", 9, "italic"),
            fg=FG_DIM, bg=BG2,
            padx=10, pady=6,
        )
        self._thinking_lbl.pack(side="left", anchor="w")
        self._scroll_to_bottom()

    def _remove_thinking_bubble(self):
        try:
            self._thinking_frame.destroy()
        except:
            pass

    def _add_error_bubble(self, error: str):
        row = tk.Frame(self._inner, bg=BG, pady=6)
        row.pack(fill="x", padx=10)

        tk.Label(row, text="MermaidBot", font=("Consolas", 7),
                 fg=FG_DIM, bg=BG).pack(side="left", anchor="nw", padx=(0, 2))

        tk.Label(
            row, text=f"Error: {error}",
            font=("Consolas", 9),
            fg=RED, bg=BG2,
            wraplength=400, justify="left",
            padx=10, pady=6,
        ).pack(side="left", anchor="w")
        self._scroll_to_bottom()

    def _add_code_bubble(self, mermaid_code: str):
        row = tk.Frame(self._inner, bg=BG, pady=6)
        row.pack(fill="x", padx=10)

        tk.Label(row, text="MermaidBot", font=("Consolas", 7),
                 fg=FG_DIM, bg=BG).pack(anchor="w", padx=(0, 2))

        # Code block frame
        code_frame = tk.Frame(row, bg=BG2,
                               highlightbackground=BG3,
                               highlightthickness=1)
        code_frame.pack(fill="x", anchor="w")

        # Horizontal scrollbar + Text widget
        hsb = tk.Scrollbar(code_frame, orient="horizontal")
        code_text = tk.Text(
            code_frame,
            font=("Consolas", 9),
            bg=BG2, fg=GREEN,
            insertbackground=BLUE,
            relief="flat",
            wrap="none",
            height=min(12, mermaid_code.count("\n") + 2),
            xscrollcommand=hsb.set,
            highlightthickness=0,
            padx=10, pady=8,
            state="normal",
        )
        hsb.config(command=code_text.xview)

        code_text.pack(fill="x")
        hsb.pack(fill="x")

        code_text.insert("1.0", mermaid_code)
        code_text.config(state="disabled")

        # Button row
        btn_row = tk.Frame(row, bg=BG2)
        btn_row.pack(fill="x", anchor="w")

        def _copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(mermaid_code)
            copy_btn.config(text="Copied!", fg=GREEN)
            self.root.after(1500, lambda: copy_btn.config(text="Copy", fg=TEAL))

        def _view():
            view_diagram_in_browser(mermaid_code)

        copy_btn = tk.Button(
            btn_row, text="Copy",
            font=("Consolas", 8),
            fg=TEAL, bg=BG2, relief="flat",
            padx=10, pady=4,
            cursor="hand2",
            activebackground=BG3,
            activeforeground=TEAL,
            command=_copy,
        )
        copy_btn.pack(side="left", padx=(6, 0), pady=4)

        view_btn = tk.Button(
            btn_row, text="View Diagram",
            font=("Consolas", 8),
            fg=PURPLE, bg=BG2, relief="flat",
            padx=10, pady=4,
            cursor="hand2",
            activebackground=BG3,
            activeforeground=PURPLE,
            command=_view,
        )
        view_btn.pack(side="left", padx=(2, 0), pady=4)

        self._scroll_to_bottom()

    # ── Scroll helper ──────────────────────────────────────────────────────────
    def _scroll_to_bottom(self):
        self.root.update_idletasks()
        self._canvas.yview_moveto(1.0)

    # ── API key prompt ─────────────────────────────────────────────────────────
    def _prompt_api_key(self):
        def _on_save():
            self._set_status("API key saved", GREEN)
            self.root.after(2000, lambda: self._set_status("ready", FG_DIM))

        show_api_key_dialog(self.root, _on_save)

    # ── Run ────────────────────────────────────────────────────────────────────
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = MermaidBot()
    app.run()
