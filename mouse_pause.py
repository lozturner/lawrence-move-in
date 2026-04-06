"""
Lawrence: Move In — Mouse Pause v1.0.0
Detects mouse idle → pops a floating action panel.
User picks what to do, or moves the mouse to dismiss.
Configurable actions, threshold, cooldown. System tray.
"""
__version__ = "2.0.0"

import json, os, queue, subprocess, sys, threading, time, tkinter as tk
from datetime import datetime
from pathlib import Path

import pystray, win32api
from PIL import Image, ImageDraw, ImageFont, ImageTk

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "mouse_pause_config.json"
NOTES_DIR   = SCRIPT_DIR / "pause_notes"
PYTHONW     = Path(sys.executable).with_name("pythonw.exe")

# ── Palette ──────────────────────────────────────────────────────────────────
BG      = "#0a0a14"
BG2     = "#12122a"
CARD    = "#1a1a3a"
CARD_HI = "#252545"
BORDER  = "#2a2a50"
TEXT    = "#cdd6f4"
DIM     = "#5a5a80"
LAVENDER= "#b4befe"
BLUE    = "#89b4fa"
GREEN   = "#a6e3a1"
PEACH   = "#fab387"
MAUVE   = "#cba6f7"
RED     = "#f38ba8"
TEAL    = "#94e2d5"
YELLOW  = "#f9e2af"
PINK    = "#f5c2e7"
SKY     = "#89dceb"

# ── Default actions ──────────────────────────────────────────────────────────
DEFAULT_ACTIONS = [
    {"name": "Quick Note",       "emoji": "📝", "color": BLUE,
     "type": "builtin",         "action": "quick_note"},
    {"name": "What Am I Doing?", "emoji": "🔍", "color": TEAL,
     "type": "launch",          "action": "watcher.py"},
    {"name": "Voice Sort",       "emoji": "🎙️", "color": PEACH,
     "type": "launch",          "action": "voicesort.py"},
    {"name": "Kidlin's Law",     "emoji": "🧠", "color": MAUVE,
     "type": "launch",          "action": "kidlin.py"},
    {"name": "Linker",           "emoji": "🔗", "color": LAVENDER,
     "type": "launch",          "action": "linker.py"},
    {"name": "Annoyances",       "emoji": "😤", "color": RED,
     "type": "builtin",         "action": "annoyances"},
    {"name": "Take a Break",     "emoji": "☕", "color": GREEN,
     "type": "builtin",         "action": "break_timer"},
    {"name": "Stretch",          "emoji": "🧘", "color": YELLOW,
     "type": "builtin",         "action": "stretch"},
    {"name": "Lock Screen",      "emoji": "🔒", "color": DIM,
     "type": "builtin",         "action": "lock_screen"},
    {"name": "Hub",              "emoji": "🏠", "color": LAVENDER,
     "type": "launch",          "action": "hub.py"},
    {"name": "Scribe",           "emoji": "✍️", "color": SKY,
     "type": "launch",          "action": "scribe.py"},
    {"name": "NACHO",            "emoji": "🧠", "color": "#cba6f7",
     "type": "launch",          "action": "nacho.py"},
    {"name": "Replay",           "emoji": "⏺️", "color": "#89b4fa",
     "type": "launch",          "action": "replay.py"},
    {"name": "Wind Down",       "emoji": "🌙", "color": "#a6e3a1",
     "type": "launch",          "action": "winddown.py"},
    {"name": "Hands Free",      "emoji": "🎤", "color": "#f9e2af",
     "type": "builtin",         "action": "hands_free"},
    {"name": "Dismiss",          "emoji": "👋", "color": DIM,
     "type": "builtin",         "action": "dismiss"},
]

# ── Config ───────────────────────────────────────────────────────────────────
def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg = {
        "idle_seconds":   8,       # how long mouse must be still
        "cooldown":       60,      # seconds before it pops again
        "move_tolerance": 5,       # px — ignore tiny mouse drift
        "actions":        DEFAULT_ACTIONS,
        "enabled":        True,
        "break_minutes":  5,
    }
    save_config(cfg)
    return cfg

def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False),
                           encoding="utf-8")

# ── Helpers ──────────────────────────────────────────────────────────────────
def hex_rgb(h):
    return int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)

def make_tray_img():
    img = Image.new("RGBA",(64,64),(0,0,0,0))
    d   = ImageDraw.Draw(img)
    d.rounded_rectangle([4,4,59,59], radius=12, fill=(180,190,254,255))
    try:    fnt = ImageFont.truetype("consola.ttf", 22)
    except: fnt = ImageFont.load_default()
    bb = d.textbbox((0,0),"MP",font=fnt)
    d.text(((64-(bb[2]-bb[0]))//2,(64-(bb[3]-bb[1]))//2),
           "MP", fill="#0a0a14", font=fnt)
    return img

# ── Main App ─────────────────────────────────────────────────────────────────
class MousePauseApp:
    def __init__(self):
        self.cfg       = load_config()
        self._alive    = True
        self._tray     = None
        self._panel    = None        # the popup Toplevel
        self._panel_up = False
        self._locked    = False       # True once user clicks — stops dismiss-on-move
        self._permanent = False       # True = panel stays forever until ✕
        self._last_pop  = 0
        self._photos   = []
        self._break_remaining = 0
        self._break_timer_id  = None

        self.root = tk.Tk()
        self.root.withdraw()         # hidden root — only the panel shows

        threading.Thread(target=self._mouse_loop, daemon=True).start()
        self._start_tray()
        self.root.mainloop()

    # ── Mouse idle loop ──────────────────────────────────────────────────
    def _mouse_loop(self):
        prev_pos   = win32api.GetCursorPos()
        idle_start = None

        while self._alive:
            time.sleep(0.3)
            if not self.cfg.get("enabled", True):
                continue

            # Re-read config each loop so changes take effect live
            tol       = self.cfg.get("move_tolerance", 5)
            threshold = self.cfg.get("idle_seconds", 8)
            cooldown  = self.cfg.get("cooldown", 60)

            try:
                pos = win32api.GetCursorPos()
            except Exception:
                continue

            dx = abs(pos[0] - prev_pos[0])
            dy = abs(pos[1] - prev_pos[1])

            if dx > tol or dy > tol:
                prev_pos = pos
                idle_start = None
                # Mouse moved — only dismiss if NOT locked AND NOT permanent
                if self._panel_up and not self._locked and not self._permanent:
                    self.root.after(0, self._dismiss_panel)
            else:
                if idle_start is None:
                    idle_start = time.time()
                elif (time.time() - idle_start >= threshold
                      and not self._panel_up
                      and time.time() - self._last_pop >= cooldown):
                    idle_start = None
                    self._last_pop = time.time()
                    self.root.after(0, self._show_panel)

    # ── Panel ────────────────────────────────────────────────────────────
    def _show_panel(self):
        if self._panel_up:
            return
        self._panel_up = True
        self._locked   = False
        self._photos.clear()

        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.attributes("-alpha", 0.0)
        p.configure(bg=BG)
        self._panel = p

        # Center on screen
        sw = p.winfo_screenwidth()
        sh = p.winfo_screenheight()

        ncols   = 4
        tile_sz = 100
        gap     = 8
        pad     = 20
        actions = self.cfg.get("actions", DEFAULT_ACTIONS)
        # +1 for the "+" custom tile
        total   = len(actions) + 1
        nrows   = -(-total // ncols)

        pw = ncols * (tile_sz + gap) + pad * 2
        ph = 60 + nrows * (tile_sz + gap) + pad + 90  # header + grid + AI box + footer
        px = (sw - pw) // 2
        py = (sh - ph) // 2
        p.geometry(f"{pw}x{ph}+{px}+{py}")

        # First click anywhere on the panel = lock it in place
        def _lock_on_click(e):
            if not self._locked:
                self._locked = True
                self._lock_lbl.config(text="🔒 Locked", fg=GREEN)

        p.bind("<Button-1>", _lock_on_click)

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(p, bg=BG2)
        hdr.pack(fill="x")

        tk.Label(hdr, text="  ⏸  You paused",
                 font=("Segoe UI",11,"bold"), fg=LAVENDER, bg=BG2,
                 anchor="w").pack(side="left", padx=10, ipady=8)

        # Close button (always works, even when locked)
        xb = tk.Label(hdr, text=" ✕ ", font=("Consolas",11),
                       fg=DIM, bg=BG2, cursor="hand2")
        xb.pack(side="right", padx=6)
        xb.bind("<Button-1>", lambda e: self._dismiss_panel())
        xb.bind("<Enter>", lambda e: xb.config(fg=RED))
        xb.bind("<Leave>", lambda e: xb.config(fg=DIM))

        now = datetime.now().strftime("%H:%M")
        tk.Label(hdr, text=now, font=("Consolas",11),
                 fg=DIM, bg=BG2).pack(side="right", padx=6, ipady=8)

        self._lock_lbl = tk.Label(hdr, text="🔓 Click to lock",
                                  font=("Segoe UI",8), fg=DIM, bg=BG2)
        self._lock_lbl.pack(side="right", padx=6)

        # ── Action grid ──────────────────────────────────────────────────
        grid = tk.Frame(p, bg=BG)
        grid.pack(fill="both", expand=True, padx=pad, pady=(pad//2, 0))

        for i in range(ncols):
            grid.columnconfigure(i, weight=1)

        for idx, act in enumerate(actions):
            row = idx // ncols
            col = idx % ncols
            self._make_tile(grid, act, tile_sz, row, col)

        # "+" Add custom tile
        plus_idx = len(actions)
        plus_row = plus_idx // ncols
        plus_col = plus_idx % ncols
        self._make_plus_tile(grid, tile_sz, plus_row, plus_col)

        # ── AI quick question box ─────────────────────────────────────────
        ai_frame = tk.Frame(p, bg=BG)
        ai_frame.pack(fill="x", padx=pad, pady=(8, 0))

        tk.Label(ai_frame, text="💬", font=("Segoe UI Emoji",11),
                 bg=BG).pack(side="left", padx=(0,4))

        self._ai_entry = tk.Entry(ai_frame, bg=CARD, fg=TEXT,
                                  insertbackground=LAVENDER, relief="flat",
                                  font=("Segoe UI",10),
                                  highlightbackground=BORDER,
                                  highlightthickness=1)
        self._ai_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self._ai_entry.insert(0, "Ask me anything…")
        self._ai_entry.config(fg=DIM)
        self._ai_entry.bind("<FocusIn>", self._ai_focus_in)
        self._ai_entry.bind("<Return>", lambda e: self._ai_ask())

        self._ai_btn = tk.Label(ai_frame, text=" Ask ", bg=LAVENDER, fg=BG,
                                font=("Segoe UI",9,"bold"), padx=8, cursor="hand2")
        self._ai_btn.pack(side="left", padx=(4,0))
        self._ai_btn.bind("<Button-1>", lambda e: self._ai_ask())

        # ── Footer ────────────────────────────────────────────────────────
        self._panel_footer = tk.Frame(p, bg=BG)
        self._panel_footer.pack(fill="x", pady=(6,10))

        self._foot_lbl = tk.Label(self._panel_footer,
                                  text="click to lock  ·  ✕ to close  ·  right-click for settings",
                                  font=("Segoe UI",7), fg=DIM, bg=BG)
        self._foot_lbl.pack()

        p.bind("<Button-3>", self._settings_menu)

        # Fade in
        self._fade_in(p, 0.0)

    def _make_tile(self, parent, act, size, row, col):
        name  = act.get("name","?")
        emoji = act.get("emoji","")
        color = act.get("color", LAVENDER)

        cell = tk.Frame(parent, bg=CARD, width=size, height=size,
                        highlightbackground=BORDER, highlightthickness=1)
        cell.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
        cell.grid_propagate(False)

        el = tk.Label(cell, text=emoji, font=("Segoe UI Emoji", 24),
                      bg=CARD, cursor="hand2")
        el.pack(pady=(14, 4))

        nl = tk.Label(cell, text=name, font=("Segoe UI", 9, "bold"),
                      fg=TEXT, bg=CARD, wraplength=size-10,
                      justify="center", cursor="hand2")
        nl.pack()

        # Hover
        def _enter(e):
            for w in (cell, el, nl): w.config(bg=CARD_HI)
            r,g,b = hex_rgb(color)
            cell.config(highlightbackground=color)
        def _leave(e):
            for w in (cell, el, nl): w.config(bg=CARD)
            cell.config(highlightbackground=BORDER)

        def _click(e):
            self._run_action(act)

        for w in (cell, el, nl):
            w.bind("<Button-1>", _click)
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)

    def _fade_in(self, win, alpha):
        if alpha >= 0.95:
            win.attributes("-alpha", 0.95)
            return
        alpha += 0.08
        win.attributes("-alpha", alpha)
        win.after(20, lambda: self._fade_in(win, alpha))

    def _fade_out(self, win, alpha, callback=None):
        if alpha <= 0.05:
            win.destroy()
            if callback: callback()
            return
        alpha -= 0.1
        win.attributes("-alpha", alpha)
        win.after(15, lambda: self._fade_out(win, alpha, callback))

    def _make_plus_tile(self, parent, size, row, col):
        cell = tk.Frame(parent, bg=CARD, width=size, height=size,
                        highlightbackground=BORDER, highlightthickness=1)
        cell.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
        cell.grid_propagate(False)

        el = tk.Label(cell, text="➕", font=("Segoe UI Emoji", 24),
                      bg=CARD, cursor="hand2")
        el.pack(pady=(14, 4))
        nl = tk.Label(cell, text="Add Custom", font=("Segoe UI", 9, "bold"),
                      fg=DIM, bg=CARD, cursor="hand2")
        nl.pack()

        def _enter(e):
            for w in (cell, el, nl): w.config(bg=CARD_HI)
        def _leave(e):
            for w in (cell, el, nl): w.config(bg=CARD)
        def _click(e):
            self._add_custom_dialog()

        for w in (cell, el, nl):
            w.bind("<Button-1>", _click)
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)

    # ── Add custom action dialog ──────────────────────────────────────────
    def _add_custom_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Add Custom Action")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.configure(bg=BG)
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"340x280+{(sw-340)//2}+{(sh-280)//2}")

        tk.Label(dlg, text="  ➕ Add Custom Action", bg=BG2, fg=LAVENDER,
                 font=("Segoe UI",10,"bold"), anchor="w").pack(fill="x", ipady=8)

        def _field(label, default=""):
            tk.Label(dlg, text=label, bg=BG, fg=DIM,
                     font=("Segoe UI",8)).pack(anchor="w", padx=12, pady=(6,1))
            e = tk.Entry(dlg, bg=CARD, fg=TEXT, insertbackground=LAVENDER,
                         relief="flat", font=("Segoe UI",10))
            e.insert(0, default)
            e.pack(fill="x", padx=12, ipady=3)
            return e

        name_e  = _field("Button name:", "My App")
        emoji_e = _field("Emoji:", "🚀")
        path_e  = _field("Full path or .py script name:", "")

        def _save():
            name  = name_e.get().strip()
            emoji = emoji_e.get().strip() or "🔧"
            path  = path_e.get().strip()
            if not name or not path:
                return

            # Determine type
            if path.endswith(".py") and not os.path.sep in path:
                act = {"name": name, "emoji": emoji, "color": LAVENDER,
                       "type": "launch", "action": path}
            else:
                act = {"name": name, "emoji": emoji, "color": LAVENDER,
                       "type": "command", "action": path}

            self.cfg["actions"].append(act)
            save_config(self.cfg)
            dlg.destroy()
            # Rebuild panel to show new tile
            self._dismiss_panel()
            self.root.after(200, self._show_panel)

        bf = tk.Frame(dlg, bg=BG)
        bf.pack(fill="x", padx=12, pady=10)
        sb = tk.Label(bf, text="Add", bg=LAVENDER, fg=BG,
                      font=("Segoe UI",9,"bold"), padx=16, pady=4, cursor="hand2")
        sb.pack(side="left")
        sb.bind("<Button-1>", lambda _: _save())
        cb = tk.Label(bf, text="Cancel", bg=CARD, fg=DIM,
                      font=("Segoe UI",9), padx=12, pady=4, cursor="hand2")
        cb.pack(side="left", padx=(8,0))
        cb.bind("<Button-1>", lambda _: dlg.destroy())
        name_e.bind("<Return>", lambda _: _save())

    # ── AI quick question ─────────────────────────────────────────────────
    def _ai_focus_in(self, e):
        if self._ai_entry.get() == "Ask me anything…":
            self._ai_entry.delete(0, "end")
            self._ai_entry.config(fg=TEXT)

    def _ai_ask(self):
        q = self._ai_entry.get().strip()
        if not q or q == "Ask me anything…":
            return

        self._ai_btn.config(text=" ⏳ ", fg=PEACH)
        self._ai_entry.config(state="disabled")

        def _run():
            try:
                api_cfg = SCRIPT_DIR / "kidlin_config.json"
                if not api_cfg.exists():
                    self.root.after(0, lambda: self._ai_show_answer("No API key in kidlin_config.json"))
                    return
                d = json.loads(api_cfg.read_text())
                api_key = d.get("api_key", "")
                model   = d.get("model", "claude-sonnet-4-20250514")
                if not api_key:
                    self.root.after(0, lambda: self._ai_show_answer("No API key set"))
                    return

                import anthropic
                cl = anthropic.Anthropic(api_key=api_key)
                r  = cl.messages.create(
                    model=model, max_tokens=200,
                    messages=[{"role":"user","content":q}])
                answer = r.content[0].text.strip()
                self.root.after(0, lambda: self._ai_show_answer(answer))
            except Exception as ex:
                self.root.after(0, lambda: self._ai_show_answer(f"Error: {ex}"))

        threading.Thread(target=_run, daemon=True).start()

    def _ai_show_answer(self, answer):
        self._ai_btn.config(text=" Ask ", fg=BG)
        self._ai_entry.config(state="normal")
        self._ai_entry.delete(0, "end")

        if not self._panel or not self._panel.winfo_exists():
            return

        import urllib.parse as up

        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.attributes("-alpha", 0.96)
        dlg.configure(bg=BG)

        px = self._panel.winfo_x()
        py = self._panel.winfo_y() + self._panel.winfo_height() + 6
        sw = dlg.winfo_screenwidth()
        dlg.geometry(f"480x280+{min(px, sw-500)}+{py}")

        tk.Label(dlg, text="  💬 Answer", bg=BG2, fg=LAVENDER,
                 font=("Segoe UI",9,"bold"), anchor="w").pack(fill="x", ipady=4)

        tk.Label(dlg, text=answer, bg=BG, fg=TEXT, font=("Segoe UI",10),
                 wraplength=450, justify="left", anchor="nw",
                 padx=12, pady=8).pack(fill="x")

        # Full action bar
        bf = tk.Frame(dlg, bg=BG)
        bf.pack(fill="x", padx=6, pady=4)

        actions = [
            ("📋 Copy", lambda: (self.root.clipboard_clear(),
                                  self.root.clipboard_append(answer),
                                  self._foot_lbl.config(text="Copied"))),
            ("📧 Email", lambda: os.startfile(
                f"mailto:?subject={up.quote('From Mouse Pause')}&body={up.quote(answer)}")),
            ("✈️ Telegram", lambda: (self.root.clipboard_clear(),
                                     self.root.clipboard_append(answer),
                                     self._safe_startfile("tg://"))),
            ("📝 Save", lambda: self._save_answer_note(answer)),
            ("📸 Screenshot", lambda: self._screenshot_active_window()),
            ("📤 JSON", lambda: (self.root.clipboard_clear(),
                                  self.root.clipboard_append(
                                      json.dumps({"source":"mouse_pause_ai",
                                                   "answer":answer,
                                                   "timestamp":datetime.now().isoformat()},
                                                  indent=2)),
                                  self._foot_lbl.config(text="JSON copied"))),
            ("Close", lambda: dlg.destroy()),
        ]

        for txt, fn in actions:
            b = tk.Label(bf, text=txt, bg=CARD, fg=TEXT,
                         font=("Segoe UI",7), padx=5, pady=3, cursor="hand2")
            b.pack(side="left", padx=1)
            b.bind("<Button-1>", lambda e, f=fn: f())
            b.bind("<Enter>", lambda e, w=b: w.config(bg="#252545"))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=CARD))

        dlg.after(60000, lambda: dlg.destroy() if dlg.winfo_exists() else None)

    def _safe_startfile(self, path):
        try: os.startfile(path)
        except: pass

    def _save_answer_note(self, text):
        d = SCRIPT_DIR / "pause_notes"
        d.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (d / f"ai_{ts}.md").write_text(
            f"# Mouse Pause AI — {datetime.now():%Y-%m-%d %H:%M}\n\n{text}\n",
            encoding="utf-8")
        self._foot_lbl.config(text="Saved to pause_notes/")

    def _screenshot_active_window(self):
        import mss
        try:
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[0])
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            d = SCRIPT_DIR / "pause_notes"
            d.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = d / f"screenshot_{ts}.jpg"
            img.save(str(path), format="JPEG", quality=75)
            self._foot_lbl.config(text=f"Screenshot: {path.name}")
        except: pass

    # ── Dismiss ───────────────────────────────────────────────────────────
    def _dismiss_panel(self):
        if not self._panel_up:
            return
        self._panel_up = False
        self._locked   = False
        if self._panel:
            try:
                self._fade_out(self._panel, 0.95)
            except Exception:
                pass
        self._panel = None

    # ── Action runners ────────────────────────────────────────────────────
    def _run_action(self, act):
        atype = act.get("type", "builtin")
        aname = act.get("action", "dismiss")

        # Dismiss the panel first
        self._dismiss_panel()

        if atype == "launch":
            script = SCRIPT_DIR / aname
            if script.exists():
                subprocess.Popen(
                    [str(PYTHONW), str(script)],
                    creationflags=0x00000008,
                    cwd=str(SCRIPT_DIR))

        elif atype == "command":
            # Run an arbitrary command
            subprocess.Popen(aname, shell=True, creationflags=0x00000008)

        elif atype == "builtin":
            fn = getattr(self, f"_act_{aname}", None)
            if fn:
                fn()

    # ── Built-in actions ──────────────────────────────────────────────────
    def _act_dismiss(self):
        pass  # already dismissed

    def _act_quick_note(self):
        NOTES_DIR.mkdir(exist_ok=True)
        dlg = tk.Toplevel(self.root)
        dlg.title("Quick Note")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.attributes("-alpha", 0.96)
        dlg.configure(bg=BG)

        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        w, h = 420, 220
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        hdr = tk.Frame(dlg, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  📝 Quick Note",
                 font=("Segoe UI",10,"bold"), fg=BLUE, bg=BG2).pack(
                     side="left", padx=8, ipady=6)
        tk.Label(hdr, text=datetime.now().strftime("%H:%M:%S"),
                 font=("Consolas",9), fg=DIM, bg=BG2).pack(
                     side="right", padx=10, ipady=6)

        txt = tk.Text(dlg, bg=CARD, fg=TEXT, insertbackground=LAVENDER,
                      font=("Segoe UI",11), wrap="word", relief="flat",
                      height=5)
        txt.pack(fill="both", expand=True, padx=10, pady=8)
        txt.focus_set()

        foot = tk.Frame(dlg, bg=BG)
        foot.pack(fill="x", padx=10, pady=(0,10))

        def _save():
            content = txt.get("1.0","end").strip()
            if content:
                ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = NOTES_DIR / f"note_{ts}.md"
                path.write_text(
                    f"# Note — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{content}\n",
                    encoding="utf-8")
            dlg.destroy()

        sb = tk.Label(foot, text="Save & Close", bg=GREEN, fg=BG,
                      font=("Segoe UI",9,"bold"), padx=16, pady=5, cursor="hand2")
        sb.pack(side="left")
        sb.bind("<Button-1>", lambda _: _save())
        cb = tk.Label(foot, text="Discard", bg=CARD, fg=DIM,
                      font=("Segoe UI",9), padx=12, pady=5, cursor="hand2")
        cb.pack(side="left", padx=(8,0))
        cb.bind("<Button-1>", lambda _: dlg.destroy())
        txt.bind("<Control-Return>", lambda _: _save())
        # Make header draggable
        for w in hdr.winfo_children():
            w.bind("<Button-1>", lambda e: setattr(dlg, '_dx', e.x) or setattr(dlg, '_dy', e.y))
            w.bind("<B1-Motion>", lambda e: dlg.geometry(
                f"+{dlg.winfo_x()+e.x-dlg._dx}+{dlg.winfo_y()+e.y-dlg._dy}"))

    def _act_annoyances(self):
        script = SCRIPT_DIR / "annoyances.py"
        if script.exists():
            subprocess.Popen(
                [str(PYTHONW), str(script)],
                creationflags=0x00000008,
                cwd=str(SCRIPT_DIR))

    def _act_break_timer(self):
        mins = self.cfg.get("break_minutes", 5)
        self._break_remaining = mins * 60

        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.attributes("-alpha", 0.93)
        dlg.configure(bg=BG)

        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        w, h = 300, 160
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        tk.Label(dlg, text="☕", font=("Segoe UI Emoji",36),
                 bg=BG).pack(pady=(16,4))
        timer_lbl = tk.Label(dlg, text="",
                             font=("Consolas",28,"bold"),
                             fg=GREEN, bg=BG)
        timer_lbl.pack()
        tk.Label(dlg, text="click to dismiss",
                 font=("Segoe UI",8), fg=DIM, bg=BG).pack(pady=(4,0))

        def _tick():
            if self._break_remaining <= 0:
                timer_lbl.config(text="Break over!", fg=PEACH)
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except Exception:
                    pass
                return
            m, s = divmod(self._break_remaining, 60)
            timer_lbl.config(text=f"{m:02d}:{s:02d}")
            self._break_remaining -= 1
            self._break_timer_id = dlg.after(1000, _tick)

        _tick()
        dlg.bind("<Button-1>", lambda _: dlg.destroy())

    def _act_stretch(self):
        stretches = [
            ("🧘 Neck roll", "Slowly roll your head in a circle. 5 each direction."),
            ("💪 Shoulder shrug", "Lift shoulders to ears, hold 3s, release. 5 times."),
            ("🤲 Wrist circles", "Extend arms, rotate wrists 10 times each way."),
            ("🦵 Stand & stretch", "Stand up. Touch toes. Hold 10 seconds."),
            ("👀 Eye break", "Look at something 20ft away for 20 seconds."),
            ("🫁 Deep breaths", "Breathe in 4s, hold 4s, out 6s. Repeat 3 times."),
        ]
        import random
        pick = random.choice(stretches)

        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.attributes("-alpha", 0.95)
        dlg.configure(bg=BG)

        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        w, h = 360, 180
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        tk.Label(dlg, text=pick[0], font=("Segoe UI Emoji",18,"bold"),
                 fg=YELLOW, bg=BG).pack(pady=(20,6))
        tk.Label(dlg, text=pick[1], font=("Segoe UI",11),
                 fg=TEXT, bg=BG, wraplength=320).pack(padx=20)
        tk.Label(dlg, text="click to dismiss",
                 font=("Segoe UI",8), fg=DIM, bg=BG).pack(pady=(12,0))
        dlg.bind("<Button-1>", lambda _: dlg.destroy())

    def _act_lock_screen(self):
        import ctypes
        ctypes.windll.user32.LockWorkStation()

    # ── Hands Free voice listener ─────────────────────────────────────────
    def _act_hands_free(self):
        """Voice module: polls for wake word 'yes' every 3s.
        If heard, transcribes in 5s chunks. End Session wraps it all up."""
        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.attributes("-alpha", 0.96)
        dlg.configure(bg=BG)

        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        w, h = 460, 420
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        hdr = tk.Frame(dlg, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  🎤 Hands Free", font=("Consolas",11,"bold"),
                 fg=YELLOW, bg=BG2).pack(side="left", padx=8, ipady=6)
        self._hf_status = tk.Label(hdr, text="starting…",
                                   font=("Segoe UI",8), fg=DIM, bg=BG2)
        self._hf_status.pack(side="left", padx=8)

        xb = tk.Label(hdr, text=" ✕ ", font=("Consolas",10),
                       fg=DIM, bg=BG2, cursor="hand2")
        xb.pack(side="right", padx=4)
        xb.bind("<Button-1>", lambda _: self._hf_stop(dlg))

        # Question prompt
        self._hf_question = tk.Label(dlg,
            text='Say "yes" to start recording your voice…',
            font=("Segoe UI",13), fg=YELLOW, bg=BG, wraplength=420, pady=12)
        self._hf_question.pack(fill="x", padx=12)

        # Transcript area
        tf = tk.Frame(dlg, bg=CARD)
        tf.pack(fill="both", expand=True, padx=10, pady=4)
        self._hf_txt = tk.Text(tf, bg="#12122a", fg=TEXT,
                                font=("Segoe UI",10), wrap="word",
                                relief="flat", state="disabled")
        self._hf_txt.pack(fill="both", expand=True, padx=4, pady=4)

        # Segment count
        self._hf_seg_lbl = tk.Label(dlg, text="0 segments recorded",
                                    font=("Segoe UI",8), fg=DIM, bg=BG)
        self._hf_seg_lbl.pack()

        # Buttons
        bf = tk.Frame(dlg, bg=BG)
        bf.pack(fill="x", padx=10, pady=6)

        end_btn = tk.Label(bf, text="🔚 End Session & Compile",
                           font=("Segoe UI",9,"bold"), fg=BG, bg=GREEN,
                           padx=12, pady=5, cursor="hand2")
        end_btn.pack(side="left")
        end_btn.bind("<Button-1>", lambda _: self._hf_end_session(dlg))

        pause_btn = tk.Label(bf, text="⏸ Pause", font=("Segoe UI",8),
                             fg=DIM, bg=CARD, padx=8, pady=4, cursor="hand2")
        pause_btn.pack(side="left", padx=6)
        self._hf_paused = False
        def _toggle_pause():
            self._hf_paused = not self._hf_paused
            pause_btn.config(text="▶ Resume" if self._hf_paused else "⏸ Pause")
        pause_btn.bind("<Button-1>", lambda _: _toggle_pause())

        # State
        self._hf_alive = True
        self._hf_segments = []
        self._hf_dlg = dlg

        # Start the wake-word loop
        threading.Thread(target=self._hf_wake_loop, daemon=True).start()

    def _hf_wake_loop(self):
        """Every 3s: open mic for 2s, listen for 'yes'. If heard, start transcription."""
        from vosk import Model, KaldiRecognizer
        import sounddevice as sd

        model_dir = SCRIPT_DIR / "vosk-model-small-en-us-0.15"
        if not model_dir.exists():
            model_dir = SCRIPT_DIR / "vosk-model-en-us-0.22-lgraph"
        if not model_dir.exists():
            self.root.after(0, lambda: self._hf_status.config(
                text="No Vosk model", fg=RED))
            return

        model = Model(str(model_dir))

        while self._hf_alive:
            if self._hf_paused:
                time.sleep(1)
                continue

            self.root.after(0, lambda: self._hf_status.config(
                text="🔇 listening for 'yes'…", fg=YELLOW))
            self.root.after(0, lambda: self._hf_question.config(
                text='Say "yes" to record, or stay silent…'))

            # Listen for 2 seconds for wake word
            heard = self._hf_listen_short(model, duration=2.0)

            if not self._hf_alive:
                break

            if heard and "yes" in heard.lower():
                # Wake word detected — start transcription segment
                self.root.after(0, lambda: self._hf_status.config(
                    text="🔴 RECORDING", fg=RED))
                self.root.after(0, lambda: self._hf_question.config(
                    text="Speak now — recording for 5 seconds…"))

                segment = self._hf_listen_short(model, duration=5.0)

                if segment and segment.strip():
                    self._hf_segments.append({
                        "timestamp": datetime.now().isoformat(),
                        "text": segment.strip()
                    })
                    self.root.after(0, lambda s=segment.strip(): self._hf_append(s))
            else:
                # No wake word — sleep 3s before next poll
                for _ in range(6):
                    if not self._hf_alive: break
                    time.sleep(0.5)

    def _hf_listen_short(self, model, duration=2.0):
        """Record for `duration` seconds and return recognized text."""
        import sounddevice as sd
        from vosk import KaldiRecognizer

        rec = KaldiRecognizer(model, 16000)
        q = queue.Queue()

        def cb(indata, frames, t, status):
            q.put(bytes(indata))

        try:
            stream = sd.RawInputStream(samplerate=16000, blocksize=4000,
                                        dtype="int16", channels=1, callback=cb)
            stream.start()
            end_time = time.time() + duration
            result = ""
            while time.time() < end_time and self._hf_alive:
                try:
                    data = q.get(timeout=0.3)
                    if rec.AcceptWaveform(data):
                        r = json.loads(rec.Result())
                        result += " " + r.get("text","")
                except queue.Empty:
                    pass
            # Get final
            final = json.loads(rec.FinalResult())
            result += " " + final.get("text","")
            stream.stop()
            stream.close()
            return result.strip()
        except Exception as e:
            return ""

    def _hf_append(self, text):
        """Append a segment to the transcript display."""
        n = len(self._hf_segments)
        self._hf_txt.config(state="normal")
        self._hf_txt.insert("end", f"[{n}] {text}\n\n")
        self._hf_txt.config(state="disabled")
        self._hf_txt.see("end")
        self._hf_seg_lbl.config(text=f"{n} segment{'s' if n!=1 else ''} recorded")

    def _hf_end_session(self, dlg):
        """End voice session — compile segments and show results."""
        self._hf_alive = False
        import urllib.parse as up

        if not self._hf_segments:
            dlg.destroy()
            return

        # Compile
        full_text = "\n".join(s["text"] for s in self._hf_segments)
        compiled = {
            "source": "hands_free_voice",
            "timestamp": datetime.now().isoformat(),
            "segment_count": len(self._hf_segments),
            "segments": self._hf_segments,
            "full_text": full_text,
        }

        # Save to file
        d = SCRIPT_DIR / "pause_notes"
        d.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = d / f"handsfree_{ts}.json"
        md_path   = d / f"handsfree_{ts}.md"

        json_path.write_text(json.dumps(compiled, indent=2, ensure_ascii=False),
                             encoding="utf-8")

        md = [f"# Hands Free Session — {datetime.now():%Y-%m-%d %H:%M}\n\n"]
        md.append(f"**Segments:** {len(self._hf_segments)}\n\n")
        for i, s in enumerate(self._hf_segments, 1):
            md.append(f"## Segment {i} — {s['timestamp'][11:19]}\n\n{s['text']}\n\n")
        md.append(f"---\n\n## Full Text\n\n{full_text}\n")
        md_path.write_text("".join(md), encoding="utf-8")

        dlg.destroy()

        # Show results popup
        res = tk.Toplevel(self.root)
        res.overrideredirect(True)
        res.attributes("-topmost", True)
        res.configure(bg=BG)
        sw, sh = res.winfo_screenwidth(), res.winfo_screenheight()
        res.geometry(f"500x350+{(sw-500)//2}+{(sh-350)//2}")

        tk.Label(res, text=f"  🎤 Session complete — {len(self._hf_segments)} segments",
                 bg=BG2, fg=GREEN, font=("Segoe UI",10,"bold"),
                 anchor="w").pack(fill="x", ipady=6)

        tk.Label(res, text=full_text[:300] + ("…" if len(full_text)>300 else ""),
                 font=("Segoe UI",10), fg=TEXT, bg=CARD, wraplength=460,
                 justify="left", anchor="nw", padx=10, pady=8).pack(
                     fill="x", padx=10, pady=6)

        # Action bar
        bf = tk.Frame(res, bg=BG)
        bf.pack(fill="x", padx=8, pady=4)
        for txt, fn in [
            ("📋 Copy text", lambda: (self.root.clipboard_clear(),
                                       self.root.clipboard_append(full_text))),
            ("📋 Copy JSON", lambda: (self.root.clipboard_clear(),
                                       self.root.clipboard_append(
                                           json.dumps(compiled, indent=2)))),
            ("📧 Email", lambda: os.startfile(
                f"mailto:?subject={up.quote('Hands Free Voice')}&body={up.quote(full_text[:1000])}")),
            ("✈️ Telegram", lambda: (self.root.clipboard_clear(),
                                     self.root.clipboard_append(full_text),
                                     self._safe_startfile("tg://"))),
            ("📁 Open", lambda: os.startfile(str(d))),
            ("Close", lambda: res.destroy()),
        ]:
            b = tk.Label(bf, text=txt, font=("Segoe UI",7), fg=TEXT, bg=CARD,
                         padx=5, pady=3, cursor="hand2")
            b.pack(side="left", padx=1)
            b.bind("<Button-1>", lambda e, f=fn: f())

        tk.Label(res, text=f"Saved: {json_path.name} + {md_path.name}",
                 font=("Consolas",7), fg=DIM, bg=BG).pack(pady=4)

    def _hf_stop(self, dlg):
        self._hf_alive = False
        dlg.destroy()

    # ── Settings menu ─────────────────────────────────────────────────────
    def _settings_menu(self, event):
        m = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT,
                    activebackground=LAVENDER, activeforeground=BG, relief="flat",
                    font=("Segoe UI", 9))

        # Timer settings with current value + bar indicator
        idle_opts = [2,3,4,5,6,8,10,12,15,20,30]
        cool_opts = [15,30,45,60,120,180,300]
        brk_opts  = [1,2,3,5,10,15,20]

        idle_cur = self.cfg.get("idle_seconds", 8)
        cool_cur = self.cfg.get("cooldown", 60)
        brk_cur  = self.cfg.get("break_minutes", 5)

        def _bar(val, opts):
            idx = opts.index(val) if val in opts else 0
            fill = "●" * (idx + 1)
            empty = "○" * (len(opts) - idx - 1)
            return f"{fill}{empty}"

        m.add_command(
            label=f"⏱  Dwell timer: {idle_cur}s  {_bar(idle_cur, idle_opts)}  (click to cycle)",
            command=lambda: (self._adjust("idle_seconds", idle_opts),
                             self._foot_lbl.config(text=f"dwell: {self.cfg['idle_seconds']}s")))
        m.add_command(
            label=f"⏳ Cooldown: {cool_cur}s  {_bar(cool_cur, cool_opts)}  (click to cycle)",
            command=lambda: (self._adjust("cooldown", cool_opts),
                             self._foot_lbl.config(text=f"cooldown: {self.cfg['cooldown']}s")))
        m.add_command(
            label=f"☕ Break timer: {brk_cur}min  {_bar(brk_cur, brk_opts)}  (click to cycle)",
            command=lambda: (self._adjust("break_minutes", brk_opts),
                             self._foot_lbl.config(text=f"break: {self.cfg['break_minutes']}min")))
        m.add_separator()
        enabled = self.cfg.get("enabled", True)
        m.add_command(
            label=f"{'⏸  Pause detection' if enabled else '▶  Resume detection'}",
            command=self._toggle_enabled)
        m.add_separator()
        m.add_command(label="⟳  Restart",  command=self._restart)
        m.add_command(label="✕  Quit",      command=self._quit)
        m.tk_popup(event.x_root, event.y_root)

    def _adjust(self, key, options):
        current = self.cfg.get(key, options[2])
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        idx = (idx + 1) % len(options)
        self.cfg[key] = options[idx]
        save_config(self.cfg)

    def _toggle_enabled(self):
        self.cfg["enabled"] = not self.cfg.get("enabled", True)
        save_config(self.cfg)

    # ── Restart ───────────────────────────────────────────────────────────
    def _restart(self):
        save_config(self.cfg)
        subprocess.Popen(
            [str(PYTHONW), str(SCRIPT_DIR / "mouse_pause.py")],
            creationflags=0x00000008,
            cwd=str(SCRIPT_DIR))
        self._quit()

    # ── Tray ──────────────────────────────────────────────────────────────
    def _start_tray(self):
        img = make_tray_img()

        def _dwell_label(_):
            return f"⏱ Dwell: {self.cfg.get('idle_seconds', 8)}s"
        def _cool_label(_):
            return f"⏳ Cooldown: {self.cfg.get('cooldown', 60)}s"
        def _perm_label(_):
            return f"{'📌 Permanent: ON' if self._permanent else '📌 Permanent: OFF'}"
        def _enabled_label(_):
            return f"{'⏸ Pause detection' if self.cfg.get('enabled', True) else '▶ Resume detection'}"

        def _cycle_dwell(icon, item):
            opts = [2,3,4,5,6,8,10,12,15,20,30]
            cur  = self.cfg.get("idle_seconds", 8)
            try:    idx = opts.index(cur)
            except: idx = 0
            self.cfg["idle_seconds"] = opts[(idx + 1) % len(opts)]
            save_config(self.cfg)

        def _cycle_cool(icon, item):
            opts = [15,30,45,60,90,120,180,300]
            cur  = self.cfg.get("cooldown", 60)
            try:    idx = opts.index(cur)
            except: idx = 0
            self.cfg["cooldown"] = opts[(idx + 1) % len(opts)]
            save_config(self.cfg)

        def _toggle_perm(icon, item):
            self._permanent = not self._permanent
            if self._permanent:
                self._locked = True
                if not self._panel_up:
                    self.root.after(0, self._show_panel)

        def _toggle_enabled(icon, item):
            self.cfg["enabled"] = not self.cfg.get("enabled", True)
            save_config(self.cfg)

        menu = pystray.Menu(
            pystray.MenuItem("Show now",
                lambda icon, item: self.root.after(0, self._show_panel_locked)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_dwell_label, _cycle_dwell),
            pystray.MenuItem(_cool_label,  _cycle_cool),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_perm_label, _toggle_perm),
            pystray.MenuItem(_enabled_label, _toggle_enabled),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⟳ Restart", lambda icon, item: self.root.after(0, self._restart)),
            pystray.MenuItem("✕ Quit",    lambda icon, item: self.root.after(0, self._quit)),
        )
        self._tray = pystray.Icon("mouse_pause", img, "Mouse Pause", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _show_panel_locked(self):
        """Show panel and immediately lock it so mouse movement won't dismiss."""
        if self._panel_up:
            return
        self._show_panel()
        self._locked = True
        if hasattr(self, '_lock_lbl'):
            self._lock_lbl.config(text="🔒 Locked", fg=GREEN)

    def _quit(self):
        self._alive = False
        if self._tray:
            self._tray.stop()
        try:
            self.root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("mouse_pause.py")
    MousePauseApp()
