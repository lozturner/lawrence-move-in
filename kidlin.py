"""
Lawrence: Move In — Kidlin's Law v1.0.0
Floating problem-clarifier widget. Always on top, auto-start.

Kidlin's Law: "If you can't clearly explain the problem,
you can't fix it. First, understand what's really wrong."

Type your messy thinking into the box, hit Ask, and Claude
helps you clarify what the actual problem is.
"""

__version__ = "1.0.0"

import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path

# --- Config ---
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "kidlin_config.json"

# --- Palette ---
BG = "#0a0a14"
BG2 = "#12122a"
CARD = "#1a1a3a"
BORDER = "#2a2a50"
TEXT = "#cdd6f4"
DIM = "#5a5a80"
ACCENT = "#cba6f7"   # mauve
GREEN = "#a6e3a1"
BLUE = "#89b4fa"
PEACH = "#fab387"
RED = "#f38ba8"
YELLOW = "#f9e2af"

KIDLIN_TEXT = (
    "If you can't clearly explain the problem, "
    "you can't fix it. First, understand what's really wrong."
)

SYSTEM_PROMPT = """You are a problem-clarification assistant based on Kidlin's Law: "If you can't clearly explain the problem, you can't fix it."

The user will describe a problem, frustration, or messy situation. Your job:

1. Cut through the noise — identify the ACTUAL core problem in 1-2 sentences
2. Restate it clearly so the user can see it plainly
3. Ask one sharp follow-up question that would help narrow it further
4. If there's an obvious first step, state it

Be direct. No waffle. Short paragraphs. Use plain language."""


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"api_key": "", "model": "claude-sonnet-4-20250514"}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


class Kidlin:
    def __init__(self):
        self.root = None
        self.config = load_config()
        self._drag_x = 0
        self._drag_y = 0
        self._asking = False

    def run(self):
        self.root = tk.Tk()
        self.root.title(f"Kidlin's Law v{__version__}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.configure(bg=BG)

        # Position: right side, upper third
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 380, 520
        x = sw - w - 20
        y = 80
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self._build()
        self._make_draggable()
        self.root.mainloop()

    def _build(self):
        # === Header ===
        hdr = tk.Frame(self.root, bg=BG2, height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self.header = hdr

        tk.Label(hdr, text="Kidlin's Law", font=("Segoe UI", 9, "bold"),
                 fg=ACCENT, bg=BG2).pack(side="left", padx=8)

        tk.Label(hdr, text=f"v{__version__}", font=("Segoe UI", 7),
                 fg=DIM, bg=BG2).pack(side="left")

        # Close
        close_btn = tk.Label(hdr, text="✕", font=("Segoe UI", 9),
                             fg=DIM, bg=BG2, padx=8, cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self._quit())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=RED))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=DIM))

        # Settings gear
        gear_btn = tk.Label(hdr, text="⚙", font=("Segoe UI", 10),
                            fg=DIM, bg=BG2, padx=4, cursor="hand2")
        gear_btn.pack(side="right")
        gear_btn.bind("<Button-1>", lambda e: self._show_settings())

        # === Law quote ===
        quote_frame = tk.Frame(self.root, bg=CARD)
        quote_frame.pack(fill="x", padx=8, pady=(8, 4))

        # Left accent bar
        tk.Frame(quote_frame, bg=YELLOW, width=3).pack(side="left", fill="y")

        quote_inner = tk.Frame(quote_frame, bg=CARD)
        quote_inner.pack(fill="x", padx=10, pady=8)

        tk.Label(quote_inner, text="1. Kidlin's Law",
                 font=("Segoe UI", 10, "bold"), fg=YELLOW, bg=CARD,
                 anchor="w").pack(fill="x")
        tk.Label(quote_inner, text=KIDLIN_TEXT,
                 font=("Segoe UI", 9), fg=TEXT, bg=CARD,
                 wraplength=320, justify="left", anchor="w").pack(fill="x", pady=(4, 0))

        # === Input area ===
        input_label = tk.Frame(self.root, bg=BG)
        input_label.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(input_label, text="What's the problem?",
                 font=("Segoe UI", 9, "bold"), fg=BLUE, bg=BG).pack(side="left")
        tk.Label(input_label, text="(messy is fine)",
                 font=("Segoe UI", 8), fg=DIM, bg=BG).pack(side="left", padx=6)

        input_frame = tk.Frame(self.root, bg=BORDER)
        input_frame.pack(fill="x", padx=8, pady=(0, 4))

        self.input_text = tk.Text(
            input_frame, height=5, bg=CARD, fg=TEXT,
            insertbackground=TEXT, font=("Segoe UI", 10),
            relief="flat", borderwidth=0, wrap="word",
            padx=8, pady=6,
        )
        self.input_text.pack(fill="x", padx=1, pady=1)
        self.input_text.bind("<Control-Return>", lambda e: self._ask())

        # === Ask button ===
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill="x", padx=8, pady=(0, 4))

        self.ask_btn = tk.Label(
            btn_frame, text="Ask Claude  ⏎",
            font=("Segoe UI", 10, "bold"),
            fg=BG, bg=ACCENT, padx=16, pady=6, cursor="hand2",
        )
        self.ask_btn.pack(side="left")
        self.ask_btn.bind("<Button-1>", lambda e: self._ask())
        self.ask_btn.bind("<Enter>", lambda e: self.ask_btn.config(bg=BLUE))
        self.ask_btn.bind("<Leave>", lambda e: self.ask_btn.config(bg=ACCENT))

        self.status_lbl = tk.Label(btn_frame, text="", font=("Segoe UI", 8),
                                   fg=DIM, bg=BG)
        self.status_lbl.pack(side="left", padx=10)

        clear_btn = tk.Label(
            btn_frame, text="Clear",
            font=("Segoe UI", 8), fg=DIM, bg=CARD,
            padx=8, pady=4, cursor="hand2",
        )
        clear_btn.pack(side="right")
        clear_btn.bind("<Button-1>", lambda e: self._clear())

        # === Response area ===
        resp_label = tk.Frame(self.root, bg=BG)
        resp_label.pack(fill="x", padx=8, pady=(4, 2))
        tk.Label(resp_label, text="The real problem:",
                 font=("Segoe UI", 9, "bold"), fg=GREEN, bg=BG).pack(side="left")

        resp_frame = tk.Frame(self.root, bg=BORDER)
        resp_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.response_text = tk.Text(
            resp_frame, bg="#0d0d1e", fg=TEXT,
            font=("Segoe UI", 10), relief="flat", borderwidth=0,
            wrap="word", padx=8, pady=6, state="disabled",
        )
        self.response_text.pack(fill="both", expand=True, padx=1, pady=1)

        # Configure text tags for styling
        self.response_text.tag_configure("bold", font=("Segoe UI", 10, "bold"), foreground=GREEN)
        self.response_text.tag_configure("question", font=("Segoe UI", 10, "italic"), foreground=PEACH)
        self.response_text.tag_configure("normal", font=("Segoe UI", 10), foreground=TEXT)

        # Check if API key is set
        if not self.config.get("api_key"):
            self._set_response("⚙ No API key set.\n\nClick the gear icon (top right) to add your Anthropic API key.\n\nGet one at console.anthropic.com")

    def _make_draggable(self):
        def start(e):
            self._drag_x, self._drag_y = e.x, e.y
        def drag(e):
            x = self.root.winfo_x() + e.x - self._drag_x
            y = self.root.winfo_y() + e.y - self._drag_y
            self.root.geometry(f"+{x}+{y}")
        for w in (self.header,) + tuple(self.header.winfo_children()):
            w.bind("<Button-1>", start)
            w.bind("<B1-Motion>", drag)

    # --- API ---

    def _ask(self):
        if self._asking:
            return

        problem = self.input_text.get("1.0", "end").strip()
        if not problem:
            self._set_response("Type something first.")
            return

        api_key = self.config.get("api_key", "")
        if not api_key:
            self._set_response("⚙ No API key.\nClick the gear icon to set it.")
            return

        self._asking = True
        self.status_lbl.config(text="Thinking...", fg=PEACH)
        self.ask_btn.config(bg=DIM, text="Thinking...")

        def do_call():
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                model = self.config.get("model", "claude-sonnet-4-20250514")

                message = client.messages.create(
                    model=model,
                    max_tokens=600,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": problem}],
                )

                reply = message.content[0].text
                self.root.after(0, lambda: self._set_response(reply))
                self.root.after(0, lambda: self.status_lbl.config(text="Done", fg=GREEN))

            except Exception as e:
                err = str(e)
                if "api_key" in err.lower() or "auth" in err.lower():
                    err = "Invalid API key. Check settings."
                self.root.after(0, lambda: self._set_response(f"Error: {err}"))
                self.root.after(0, lambda: self.status_lbl.config(text="Error", fg=RED))
            finally:
                self._asking = False
                self.root.after(0, lambda: self.ask_btn.config(bg=ACCENT, text="Ask Claude  ⏎"))

        threading.Thread(target=do_call, daemon=True).start()

    def _set_response(self, text):
        self.response_text.config(state="normal")
        self.response_text.delete("1.0", "end")
        self.response_text.insert("1.0", text)
        self.response_text.config(state="disabled")

    def _clear(self):
        self.input_text.delete("1.0", "end")
        self._set_response("")
        self.status_lbl.config(text="")

    # --- Settings ---

    def _show_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Kidlin Settings")
        win.configure(bg=BG)
        win.geometry("360x220")
        win.attributes("-topmost", True)
        win.resizable(False, False)

        tk.Label(win, text="Settings", font=("Segoe UI", 12, "bold"),
                 fg=ACCENT, bg=BG).pack(pady=(12, 8))

        # API key
        tk.Label(win, text="Anthropic API Key:",
                 font=("Segoe UI", 9), fg=TEXT, bg=BG).pack(anchor="w", padx=16)

        key_var = tk.StringVar(value=self.config.get("api_key", ""))
        key_entry = tk.Entry(win, textvariable=key_var, bg=CARD, fg=TEXT,
                             insertbackground=TEXT, font=("Consolas", 9),
                             relief="flat", show="•")
        key_entry.pack(fill="x", padx=16, pady=(2, 8), ipady=4)

        # Model
        tk.Label(win, text="Model:",
                 font=("Segoe UI", 9), fg=TEXT, bg=BG).pack(anchor="w", padx=16)

        model_var = tk.StringVar(value=self.config.get("model", "claude-sonnet-4-20250514"))
        model_entry = tk.Entry(win, textvariable=model_var, bg=CARD, fg=TEXT,
                               insertbackground=TEXT, font=("Consolas", 9),
                               relief="flat")
        model_entry.pack(fill="x", padx=16, pady=(2, 12), ipady=4)

        # Show/hide key toggle
        showing = [False]
        def toggle_show():
            showing[0] = not showing[0]
            key_entry.config(show="" if showing[0] else "•")
            show_btn.config(text="Hide" if showing[0] else "Show")

        show_btn = tk.Label(win, text="Show", font=("Segoe UI", 8),
                            fg=BLUE, bg=BG, cursor="hand2")
        show_btn.place(x=320, y=62)
        show_btn.bind("<Button-1>", lambda e: toggle_show())

        def do_save():
            self.config["api_key"] = key_var.get().strip()
            self.config["model"] = model_var.get().strip()
            save_config(self.config)
            win.destroy()
            self._set_response("Settings saved. Ready to clarify problems.")
            self.status_lbl.config(text="Key saved", fg=GREEN)

        save_btn = tk.Label(win, text="Save", font=("Segoe UI", 10, "bold"),
                            fg=BG, bg=GREEN, padx=20, pady=6, cursor="hand2")
        save_btn.pack(pady=(0, 12))
        save_btn.bind("<Button-1>", lambda e: do_save())

    def _quit(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("kidlin.py")
    Kidlin().run()
