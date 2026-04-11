"""
Lawrence: Move In -- Level 4: Gallery Launcher v2.1.0
Visual gallery of every applet. Click any card to launch it instantly.
"Launch All" fires everything. "+ Add App" is one paste, one Enter.

Usage:
  python launch_gallery.py
  python launch_level.py 4
"""
__version__ = "2.1.0"
import selfclean; selfclean.ensure_single("launch_gallery.py")

import json, os, subprocess, sys, time, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont
import mss

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHONW    = Path(sys.executable).with_name("pythonw.exe")
DETACHED   = 0x00000008
THUMB_DIR  = SCRIPT_DIR / "thumbnails"
THUMB_DIR.mkdir(exist_ok=True)
EXTERNAL_CONFIG = SCRIPT_DIR / "external_apps.json"

EXTERNAL_COLORS = ["#f5c2e7", "#89dceb", "#fab387", "#f9e2af", "#a6e3a1",
                    "#b4befe", "#cba6f7", "#94e2d5", "#89b4fa", "#f38ba8"]

# -- App catalogue ----------------------------------------------------------------
APPS = [
    {"script": "hot_corner.py", "name": "Hot Corners", "icon": "HC", "color": "#a6e3a1", "level": 1,
     "problem": "Windows has no hot corners. Mac does. You want screen corner triggers.",
     "solution": "Move your mouse to any corner -- triggers actions. Alt+Tab, Task View, Telegram, or run any file you pick.",
     "category": "Window Management"},
    {"script": "niggly.py", "name": "Focus Rules", "icon": "NM", "color": "#a6e3a1", "level": 1,
     "problem": "Focus one window, lose three others. No concept of window pairing.",
     "solution": "IF/THEN cards: 'When I focus VS Code, minimise Chrome.' Polls every 150ms, enforces silently.",
     "category": "Window Management"},
    {"script": "tiles.py", "name": "Window Tiles", "icon": "TL", "color": "#94e2d5", "level": 1,
     "problem": "No visual map of what's open. Taskbar shows tiny useless icons.",
     "solution": "Every window as a coloured tile, grouped by type. Desktop canvas mode with passthrough ghost overlay.",
     "category": "Window Management"},
    {"script": "app_tray.py", "name": "App Tray", "icon": "AT", "color": "#89b4fa", "level": 1,
     "problem": "Your most-used apps have no permanent tray icons with real logos.",
     "solution": "Real icons extracted from .exe files sitting in your system tray. One right-click to open.",
     "category": "Window Management"},
    {"script": "nag.py", "name": "Nag", "icon": "NG", "color": "#f9e2af", "level": 1,
     "problem": "You forget what you should be doing. No timetable nagger exists.",
     "solution": "Pops up every 5 minutes: 'Hey, it's 14:30. You should be doing X.' Linked to Google Calendar.",
     "category": "Productivity"},
    {"script": "hub.py", "name": "Hub", "icon": "HB", "color": "#b4befe", "level": 2,
     "problem": "Too many applets, no single place to see or launch them.",
     "solution": "Steam Deck-style tile grid. Green dot = running. Click to launch. Triple-click to hard reset.",
     "category": "Productivity"},
    {"script": "linker.py", "name": "Linker", "icon": "LK", "color": "#b4befe", "level": 2,
     "problem": "You use the same connector phrases but can never find them mid-thought.",
     "solution": "Clickable phrase tiles. Multi-select, zoom, AI auto-suggest from screenshot. Click = clipboard.",
     "category": "Productivity"},
    {"script": "mouse_pause.py", "name": "Mouse Pause", "icon": "MP", "color": "#f5c2e7", "level": 2,
     "problem": "You sit back. The computer doesn't notice. No bridge to 'what next?'",
     "solution": "Detects idle mouse. Action panel pops up. Hands-free voice, AI input, custom tiles. Click to lock.",
     "category": "AI & Voice"},
    {"script": "scribe.py", "name": "Scribe", "icon": "SC", "color": "#89dceb", "level": 2,
     "problem": "Ideas flow when you speak. But STT is buried in menus and needs internet.",
     "solution": "Floating always-on speech-to-text. Offline Vosk. Auto-tags content. Copy anywhere.",
     "category": "AI & Voice"},
    {"script": "voicesort.py", "name": "Voice Sort", "icon": "VS", "color": "#fab387", "level": 2,
     "problem": "Thoughts vanish. Clipboard copies disappear. Nothing gets categorised.",
     "solution": "Catches every Ctrl+C. Claude sorts into thought/task/idea/rant. Files to markdown automatically.",
     "category": "AI & Voice"},
    {"script": "kidlin.py", "name": "Kidlin's Law", "icon": "KL", "color": "#f9e2af", "level": 2,
     "problem": "You can't articulate the actual problem. ADHD brain tangles everything.",
     "solution": "Type messy thinking. Claude returns: 'The actual problem is...' -- clean, actionable, shareable.",
     "category": "AI & Voice"},
    {"script": "watcher.py", "name": "Watcher", "icon": "WA", "color": "#89b4fa", "level": 3,
     "problem": "You zone out and forget what you were doing. Nobody's watching.",
     "solution": "Mouse stops 3 seconds -> screenshot -> Claude Vision reads what's on screen and tells you.",
     "category": "AI & Voice"},
    {"script": "nacho.py", "name": "NACHO", "icon": "NA", "color": "#cba6f7", "level": 3,
     "problem": "No one to talk to when you're stuck. Typing into ChatGPT is too slow.",
     "solution": "Voice AI. Speaks to you by name. You talk, it listens. Every sentence is a clickable hyperlink.",
     "category": "AI & Voice"},
    {"script": "replay.py", "name": "Replay", "icon": "RP", "color": "#89b4fa", "level": 3,
     "problem": "Can't remember what you did an hour ago. No record, no trail, no proof.",
     "solution": "Screenshots every 10s. Mouse trail. Window log. Clipboard. Scrub timeline. Export report.",
     "category": "Session Management"},
    {"script": "capture.py", "name": "Capture", "icon": "CP", "color": "#fab387", "level": 3,
     "problem": "You need to brain-dump a screenshot + notes but there's no quick tool.",
     "solution": "Click tray -> screenshot + notes popup. Sessions bundle captures. AI processes on export.",
     "category": "Session Management"},
    {"script": "winddown.py", "name": "Winddown", "icon": "WD", "color": "#94e2d5", "level": 3,
     "problem": "You don't know how to walk away. Nothing verifies you're done.",
     "solution": "Scans everything open. Auto-checklist. AI verifies loose ends. Saves state. Resumes next day.",
     "category": "Session Management"},
    {"script": "annoyances.py", "name": "Annoyances", "icon": "AN", "color": "#f38ba8", "level": 3,
     "problem": "Computer annoyances pile up. You grumble and forget. Never logged, never fixed.",
     "solution": "Persistent checklist. Text/voice/screenshot input. AI suggests workarounds. Exports to markdown.",
     "category": "Session Management"},
    {"script": "launcher.py", "name": "Master Launcher", "icon": "MI", "color": "#cba6f7", "level": 3,
     "problem": "No motivation to use your own tools. No feedback loop.",
     "solution": "Gamification. Glowing orbs. XP ring. Level up by using your suite. Progress bars and unlocks.",
     "category": "Session Management"},
    {"script": "aitimer.py", "name": "AI Timer", "icon": "AT", "color": "#f9e2af", "level": 2,
     "problem": "You open 4 LLM chats, scatter between them, lose track of time and which ones are done.",
     "solution": "Multiple concurrent timers. Auto-detects AI windows. Periodic check-in popups. Jump-back button to return to any tracked window. Exports time log.",
     "category": "Productivity"},
    {"script": "steps.py", "name": "Steps Recorder", "icon": "ST", "color": "#f5c2e7", "level": 3,
     "problem": "Windows Steps Recorder is dead. You need to document what you clicked and why.",
     "solution": "Records every click, keystroke, window switch with screenshots, handles, PIDs, clipboard. Navigable step-by-step viewer. Exports to JSON and markdown.",
     "category": "Session Management"},
    {"script": "laurence_triclick.exe", "name": "TriClick", "icon": "TC", "color": "#fab387", "level": 2,
     "problem": "You say what you want the computer to do. It doesn't happen. No way to train it.",
     "solution": "Triple right-click anywhere. Voice command via Whisper. Train button maps phrases to actions. Builds a personal command dataset. Browser tab switcher in tray.",
     "category": "AI & Voice"},
]

CATEGORIES = ["Window Management", "Productivity", "AI & Voice", "Session Management", "External Tools"]
CAT_COLORS = {
    "Window Management": "#a6e3a1", "Productivity": "#b4befe",
    "AI & Voice": "#89b4fa", "Session Management": "#94e2d5", "External Tools": "#f5c2e7",
}

# -- External apps persistence ----------------------------------------------------
def load_external_apps():
    if not EXTERNAL_CONFIG.exists():
        return []
    try:
        with open(EXTERNAL_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f).get("apps", [])
    except Exception:
        return []

def save_external_apps(apps):
    try:
        with open(EXTERNAL_CONFIG, "w", encoding="utf-8") as f:
            json.dump({"apps": apps, "version": "1.0"}, f, indent=2)
        return True
    except Exception as e:
        print(f"Save error: {e}")
        return False

def get_all_apps():
    return APPS + load_external_apps()

# -- Helpers -----------------------------------------------------------------------
def get_running():
    import psutil
    running = set()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
            if len(cmd) > 1 and "niggly_machine" in cmd[1] and "python" in (p.info["name"] or "").lower():
                running.add(os.path.basename(cmd[1]))
        except: pass
    return running

def kill_all_suite():
    import psutil
    my = os.getpid()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        if p.info["pid"] == my: continue
        try:
            cmd = p.info["cmdline"] or []
            if len(cmd) > 1 and "niggly_machine" in cmd[1] and "python" in (p.info["name"] or "").lower():
                p.kill()
        except: pass

def _launch_path(path_str, cwd=None):
    """Universal launcher: handles .py, .lnk, .url, .bat, .cmd, .ps1, http://, fallback os.startfile.
    Returns subprocess.Popen or None."""
    if path_str.startswith(("http://", "https://")):
        os.startfile(path_str)
        return None
    p = Path(path_str)
    ext = p.suffix.lower()
    work = cwd or str(p.parent)
    if ext == ".py":
        return subprocess.Popen([str(PYTHONW), str(p)], creationflags=DETACHED, cwd=work)
    elif ext in (".bat", ".cmd"):
        return subprocess.Popen(["cmd", "/c", str(p)], creationflags=DETACHED, cwd=work)
    elif ext == ".ps1":
        return subprocess.Popen(["powershell", "-File", str(p)], creationflags=DETACHED, cwd=work)
    else:  # .lnk, .url, .exe, anything else
        os.startfile(str(p))
        return None

def make_placeholder_thumb(app, size=(280, 160)):
    w, h = size
    col = app["color"]
    r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
    # Fast gradient: dark base blended with a tinted overlay
    base = Image.new("RGB", (w, h), (0, 0, 0))
    tint = Image.new("RGB", (w, h), (int(r * 0.3), int(g * 0.3), int(b * 0.3)))
    img = Image.blend(base, tint, 1.0)
    # Vertical gradient via alpha composite
    gradient = Image.new("L", (1, h))
    for y in range(h):
        gradient.putpixel((0, y), int(255 * y / h))
    gradient = gradient.resize((w, h), Image.NEAREST)
    black = Image.new("RGB", (w, h), (0, 0, 0))
    img = Image.composite(img, black, gradient)

    draw = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2 - 10
    rc = 30
    draw.ellipse([cx - rc, cy - rc, cx + rc, cy + rc], fill=col, outline=col)
    try: font = ImageFont.truetype("consola.ttf", 20)
    except: font = ImageFont.load_default()
    bb = draw.textbbox((0, 0), app["icon"], font=font)
    draw.text((cx - (bb[2]-bb[0])//2, cy - (bb[3]-bb[1])//2), app["icon"], fill="#1e1e2e", font=font)
    try: nfont = ImageFont.truetype("segoeui.ttf", 14)
    except: nfont = font
    bb2 = draw.textbbox((0, 0), app["name"], font=nfont)
    draw.text((cx - (bb2[2]-bb2[0])//2, cy + rc + 10), app["name"], fill="#cdd6f4", font=nfont)
    return img

# -- Gallery Window ----------------------------------------------------------------
class GalleryLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Lawrence: Move In -- Level 4 Gallery v{__version__}")
        self.root.configure(bg="#f8f8fc")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = min(1100, sw - 80), min(820, sh - 80)
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.root.minsize(700, 500)

        self.thumb_imgs = {}
        self.thumb_labels = {}
        self._status_dot_canvas = {}
        self._running = set()
        self._prev_running = set()
        self._app_lookup = {}

        self._build_ui()
        self._load_thumbnails_async()
        self._poll_running()

    # -- Dialog helper -------------------------------------------------------------
    def _dialog(self, title, w, h, *, geometry=None):
        """Create a styled Toplevel dialog, centred on screen."""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg="#ffffff")
        dlg.attributes("-topmost", True)
        dlg.transient(self.root)
        if geometry:
            dlg.geometry(geometry)
        else:
            sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
            dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        dlg.resizable(False, False)
        return dlg

    # -- UI building ---------------------------------------------------------------
    def _build_ui(self):
        root = self.root

        # Header
        hdr = tk.Frame(root, bg="#ffffff", padx=20, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Lawrence: Move In",
                 font=("Segoe UI", 22, "bold"), fg="#4a3f6b", bg="#ffffff").pack(side="left")
        tk.Label(hdr, text="Level 4 -- Full Gallery",
                 font=("Segoe UI", 12), fg="#8b82a8", bg="#ffffff", padx=16).pack(side="left")

        btn_frame = tk.Frame(hdr, bg="#ffffff")
        btn_frame.pack(side="right")
        self.run_btn = tk.Button(btn_frame, text="\u25b6  Launch All",
                    font=("Segoe UI", 11, "bold"), fg="#ffffff", bg="#6c5ce7",
                    activeforeground="#ffffff", activebackground="#5a4bd1",
                    relief="flat", padx=20, pady=6, cursor="hand2",
                    command=self._launch_all)
        self.run_btn.pack(side="right", padx=(8, 0))
        tk.Button(btn_frame, text="+ Add App",
                  font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#f5c2e7",
                  activeforeground="#ffffff", activebackground="#e8a7d4",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  command=self._show_add_dialog).pack(side="right", padx=(4, 8))

        tk.Frame(root, bg="#e8e6f0", height=2).pack(fill="x")

        # Status bar
        self.status_frame = tk.Frame(root, bg="#faf9ff", padx=20, pady=8)
        self.status_frame.pack(fill="x")
        self.status_label = tk.Label(self.status_frame, text="Loading thumbnails...",
                                      font=("Segoe UI", 9), fg="#8b82a8", bg="#faf9ff")
        self.status_label.pack(side="left")
        self.count_label = tk.Label(self.status_frame, text="0 running",
                                     font=("Segoe UI", 9, "bold"), fg="#6c5ce7", bg="#faf9ff")
        self.count_label.pack(side="right")

        # Scrollable gallery
        container = tk.Frame(root, bg="#f8f8fc")
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg="#f8f8fc", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg="#f8f8fc")
        self.scroll_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        self._canvas = canvas

        self._populate_cards()

    def _populate_cards(self):
        """Build category headers and app cards into scroll_frame."""
        all_apps = get_all_apps()
        self._all_apps_cache = all_apps
        for cat in CATEGORIES:
            cat_apps = [a for a in all_apps if a.get("category") == cat]
            if not cat_apps:
                continue
            cat_color = CAT_COLORS.get(cat, "#888")

            cat_frame = tk.Frame(self.scroll_frame, bg="#f8f8fc")
            cat_frame.pack(fill="x", padx=20, pady=(20, 4))
            dot = tk.Canvas(cat_frame, width=12, height=12, bg="#f8f8fc", highlightthickness=0)
            dot.create_oval(2, 2, 10, 10, fill=cat_color, outline=cat_color)
            dot.pack(side="left", padx=(0, 8))
            tk.Label(cat_frame, text=cat.upper(),
                     font=("Segoe UI", 10, "bold"), fg="#4a3f6b",
                     bg="#f8f8fc", anchor="w").pack(side="left")
            tk.Label(cat_frame, text=f"{len(cat_apps)} apps",
                     font=("Segoe UI", 9), fg="#aaa",
                     bg="#f8f8fc").pack(side="left", padx=8)

            tk.Frame(self.scroll_frame, bg=cat_color, height=2).pack(fill="x", padx=20, pady=(0, 8))

            grid_frame = tk.Frame(self.scroll_frame, bg="#f8f8fc")
            grid_frame.pack(fill="x", padx=16)
            for i, app in enumerate(cat_apps):
                self._make_card(grid_frame, app, i)

        footer = tk.Frame(self.scroll_frame, bg="#f8f8fc", pady=16)
        footer.pack(fill="x", padx=20)
        tk.Label(footer, text="Click any card to launch it. 'Launch All' fires everything.",
                 font=("Segoe UI", 9), fg="#aaa", bg="#f8f8fc").pack()
        tk.Label(footer, text="Built by Loz Turner \u00b7 2026 \u00b7 Lawrence: Move In",
                 font=("Segoe UI", 8), fg="#ccc", bg="#f8f8fc").pack()

    def _rebuild_gallery(self):
        """Clear scroll_frame and repopulate. Called after add/edit/delete."""
        try:
            for child in self.scroll_frame.winfo_children():
                child.destroy()
            self.thumb_imgs = {}
            self.thumb_labels = {}
            self._status_dot_canvas = {}
            self._app_lookup = {}
            self._populate_cards()
            self._load_thumbnails_async()
            self._update_running_count()
        except tk.TclError:
            pass

    def _make_card(self, parent, app, index):
        col = app["color"]
        script = app["script"]
        self._app_lookup[script] = app

        card = tk.Frame(parent, bg="#ffffff", padx=0, pady=0,
                        relief="flat", highlightthickness=1,
                        highlightbackground="#e8e6f0", cursor="hand2")
        card.grid(row=index // 3, column=index % 3, padx=8, pady=8, sticky="nsew")
        parent.grid_columnconfigure(index % 3, weight=1)

        tk.Frame(card, bg=col, height=4).pack(fill="x")
        inner = tk.Frame(card, bg="#ffffff", padx=14, pady=10, cursor="hand2")
        inner.pack(fill="both", expand=True)

        # Top row: name + badge + status dot
        top = tk.Frame(inner, bg="#ffffff")
        top.pack(fill="x")
        tk.Label(top, text=app["name"], font=("Segoe UI", 11, "bold"), fg="#2d2740",
                 bg="#ffffff", cursor="hand2").pack(side="left", padx=(4, 0))

        is_external = app.get("external", False)
        if is_external:
            badge_bg, badge_text = "#f5c2e7", " EXT "
        else:
            badge_bg = {1: "#a6e3a1", 2: "#89b4fa", 3: "#cba6f7", 4: "#f9e2af"}.get(app["level"], "#888")
            badge_text = f" L{app['level']} "
        tk.Label(top, text=badge_text, font=("Consolas", 8, "bold"),
                 fg="#1e1e2e", bg=badge_bg).pack(side="right")

        dot_c = tk.Canvas(top, width=10, height=10, bg="#ffffff", highlightthickness=0)
        dot_c.pack(side="right", padx=4)
        self._status_dot_canvas[script] = dot_c

        # Thumbnail
        thumb_frame = tk.Frame(inner, bg="#e8e6f0", width=252, height=142, cursor="hand2")
        thumb_frame.pack(fill="x", pady=(8, 6))
        thumb_frame.pack_propagate(False)
        thumb_label = tk.Label(thumb_frame, bg="#e8e6f0", text="Loading...",
                               font=("Segoe UI", 9), fg="#aaa", cursor="hand2")
        thumb_label.pack(expand=True)
        self.thumb_labels[script] = thumb_label

        # Problem
        prob_frame = tk.Frame(inner, bg="#fff5f5", padx=8, pady=6)
        prob_frame.pack(fill="x", pady=(4, 2))
        tk.Label(prob_frame, text="THE PROBLEM", font=("Segoe UI", 7, "bold"),
                 fg="#e64553", bg="#fff5f5", anchor="w").pack(fill="x")
        tk.Label(prob_frame, text=app["problem"], font=("Segoe UI", 8), fg="#6e5a5a",
                 bg="#fff5f5", wraplength=220, justify="left", anchor="w").pack(fill="x")

        # Solution
        r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
        sol_bg = f"#{min(r+220,255):02x}{min(g+220,255):02x}{min(b+220,255):02x}"
        sol_frame = tk.Frame(inner, bg=sol_bg, padx=8, pady=6)
        sol_frame.pack(fill="x", pady=(2, 4))
        tk.Label(sol_frame, text="THE SOLUTION", font=("Segoe UI", 7, "bold"),
                 fg=col, bg=sol_bg, anchor="w").pack(fill="x")
        tk.Label(sol_frame, text=app["solution"], font=("Segoe UI", 8), fg="#3a3a4a",
                 bg=sol_bg, wraplength=220, justify="left", anchor="w").pack(fill="x")

        # Script path display
        if is_external:
            dp = app.get("path", "")
            path_text = f"\u2197 {'...' + dp[-39:] if len(dp) > 42 else dp}"
        else:
            path_text = app["script"]
        tk.Label(inner, text=path_text, font=("Consolas", 8), fg="#aaa",
                 bg="#ffffff", anchor="w").pack(fill="x")

        # Click bindings
        def _click(e, a=app): self._launch_single(a)
        def _menu(e, a=app):
            menu = tk.Menu(self.root, tearoff=0)
            if a.get("external"):
                menu.add_command(label=f"Launch {a['name']}", command=lambda: self._launch_single(a))
                menu.add_separator()
                menu.add_command(label="Edit...", command=lambda: self._edit_external_dialog(a))
                menu.add_command(label="Recapture thumbnail...", command=lambda: self._choose_thumbnail_method(a))
                menu.add_separator()
                menu.add_command(label="Delete", command=lambda: self._delete_external(a))
            else:
                menu.add_command(label=f"Launch {a['name']}", command=lambda: self._launch_single(a))
            try: menu.tk_popup(e.x_root, e.y_root)
            finally: menu.grab_release()

        for w in [card, inner, thumb_frame, thumb_label]:
            w.bind("<Button-1>", _click)
            w.bind("<Button-3>", _menu)

    # -- Running status ------------------------------------------------------------
    def _update_running_count(self):
        self.count_label.config(text=f"{len(self._running)} running")

    def _poll_running(self):
        try:
            self._running = get_running()
            changed = self._running ^ self._prev_running
            for script in changed:
                dot_c = self._status_dot_canvas.get(script)
                if not dot_c: continue
                try:
                    dot_c.delete("all")
                    fill = "#00b894" if script in self._running else "#ddd"
                    dot_c.create_oval(1, 1, 9, 9, fill=fill, outline=fill)
                except tk.TclError: pass
            # First run: paint all dots
            if not self._prev_running and not changed:
                for script, dot_c in self._status_dot_canvas.items():
                    try:
                        dot_c.delete("all")
                        fill = "#00b894" if script in self._running else "#ddd"
                        dot_c.create_oval(1, 1, 9, 9, fill=fill, outline=fill)
                    except tk.TclError: pass
            self._prev_running = set(self._running)
            self._update_running_count()
            cur = self.status_label.cget("text")
            if "Gallery ready" in cur or "running" in cur:
                self.status_label.config(text=f"Gallery ready -- {len(self._running)} apps currently running")
            self.root.after(3000, self._poll_running)
        except tk.TclError: pass

    # -- Thumbnails ----------------------------------------------------------------
    def _load_thumbnails_async(self):
        def _load():
            for app in get_all_apps():
                script = app["script"]
                if script in self.thumb_imgs and script in self.thumb_labels:
                    try:
                        if self.thumb_labels[script].cget("image"):
                            continue
                    except tk.TclError: pass

                if app.get("external") and app.get("thumb_path"):
                    thumb_path = Path(app["thumb_path"])
                else:
                    safe_name = script.replace(".py", "").replace("external:", "ext_").replace(":", "_").replace("/", "_").replace("\\", "_")
                    thumb_path = THUMB_DIR / f"{safe_name}.png"

                if not thumb_path.exists():
                    img = make_placeholder_thumb(app, size=(252, 142))
                    img.save(str(thumb_path))
                try:
                    img = Image.open(str(thumb_path)).resize((252, 142), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.thumb_imgs[script] = photo
                    if script in self.thumb_labels:
                        try: self.thumb_labels[script].config(image=photo, text="")
                        except tk.TclError: pass
                except Exception: pass
            try: self.status_label.config(text="Gallery ready -- click any card to launch")
            except tk.TclError: pass
        threading.Thread(target=_load, daemon=True).start()

    # -- Launch --------------------------------------------------------------------
    def _launch_single(self, app, quiet=False):
        try:
            if app.get("external"):
                path_str = app.get("path", "")
                if not path_str: return
                _launch_path(path_str)
            else:
                script = app["script"]
                if script.endswith(".exe"):
                    # Native binary — launch directly
                    path = SCRIPT_DIR / script
                    if path.exists():
                        subprocess.Popen([str(path)], creationflags=DETACHED, cwd=str(SCRIPT_DIR))
                else:
                    selfclean.safe_launch(script)
            if not quiet:
                self.status_label.config(text=f"Launched {app['name']}")
        except Exception as e:
            if not quiet:
                self.status_label.config(text=f"Launch failed: {e}")

    def _launch_all(self):
        all_apps = get_all_apps()
        if not all_apps:
            self.status_label.config(text="No apps to launch")
            return
        kill_all_suite()
        time.sleep(0.5)
        launched = 0
        for app in all_apps:
            try:
                self._launch_single(app, quiet=True)
                launched += 1
                time.sleep(0.3)
            except Exception as e:
                print(f"Failed to launch {app.get('name')}: {e}")
        self.status_label.config(text=f"Launched {launched} apps")

    # -- External app management ---------------------------------------------------
    def _ext_thumb_path(self, app):
        safe = app["script"].replace("external:", "ext_").replace(":", "_").replace("/", "_").replace("\\", "_")
        return THUMB_DIR / f"{safe}.png"

    def _save_thumb_path(self, app, thumb_path):
        """Update an external app's thumb_path in the JSON config."""
        externals = load_external_apps()
        for e in externals:
            if e["script"] == app["script"]:
                e["thumb_path"] = str(thumb_path)
                break
        save_external_apps(externals)

    def _show_add_dialog(self):
        dlg = self._dialog("Add App", 480, 180)

        hdr = tk.Frame(dlg, bg="#f5c2e7", pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="+ Add App", font=("Segoe UI", 13, "bold"),
                 fg="#2d2740", bg="#f5c2e7").pack()

        body = tk.Frame(dlg, bg="#ffffff", padx=20, pady=14)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Paste a URL, path, or shortcut:",
                 font=("Segoe UI", 9), fg="#4a3f6b", bg="#ffffff", anchor="w").pack(fill="x", pady=(0, 6))

        input_var = tk.StringVar()
        entry = tk.Entry(body, textvariable=input_var, font=("Segoe UI", 11),
                         relief="flat", bg="#f8f8fc", highlightthickness=2,
                         highlightbackground="#e8e6f0", highlightcolor="#6c5ce7")
        entry.pack(fill="x")
        entry.focus_set()

        btn_row = tk.Frame(body, bg="#ffffff", pady=8)
        btn_row.pack(fill="x")

        def _add_app(*_):
            raw = input_var.get().strip()
            if not raw: return
            if raw.startswith(("http://", "https://")):
                try:
                    from urllib.parse import urlparse
                    parts = urlparse(raw).netloc.replace("www.", "").split(".")
                    name = parts[0].capitalize() if parts else "App"
                except Exception: name = "Web App"
            else:
                name = Path(raw).stem.replace("_", " ").replace("-", " ").title()

            words = name.split()
            icon = (words[0][0] + words[1][0]).upper() if len(words) >= 2 else name[:2].upper()
            externals = load_external_apps()
            color = EXTERNAL_COLORS[len(externals) % len(EXTERNAL_COLORS)]
            script_id = f"external:{int(time.time() * 1000)}"
            new_app = {
                "script": script_id, "name": name, "path": raw,
                "icon": icon, "color": color, "level": 4,
                "problem": "An external tool you use regularly.",
                "solution": "One-click launch from the gallery.",
                "category": "External Tools", "external": True,
            }
            externals.append(new_app)
            save_external_apps(externals)

            thumb_path = self._ext_thumb_path(new_app)
            make_placeholder_thumb(new_app, size=(252, 142)).save(str(thumb_path))
            self._save_thumb_path(new_app, thumb_path)

            dlg.destroy()
            self.status_label.config(text=f"Added {name}")
            self._rebuild_gallery()

        entry.bind("<Return>", _add_app)
        tk.Button(btn_row, text="Add", font=("Segoe UI", 10, "bold"),
                  fg="#ffffff", bg="#6c5ce7", relief="flat", padx=20, pady=4,
                  cursor="hand2", command=_add_app).pack(side="right", padx=4)
        tk.Button(btn_row, text="Cancel", font=("Segoe UI", 10),
                  fg="#888", bg="#f0f0f5", relief="flat", padx=14, pady=4,
                  cursor="hand2", command=dlg.destroy).pack(side="right")

    def _edit_external_dialog(self, editing):
        dlg = self._dialog(f"Edit: {editing['name']}", 480, 300)

        hdr = tk.Frame(dlg, bg="#f5c2e7", pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"Edit: {editing['name']}",
                 font=("Segoe UI", 13, "bold"), fg="#2d2740", bg="#f5c2e7").pack()

        body = tk.Frame(dlg, bg="#ffffff", padx=20, pady=10)
        body.pack(fill="both", expand=True)

        def _field(parent, label, default=""):
            tk.Label(parent, text=label, font=("Segoe UI", 9, "bold"),
                     fg="#4a3f6b", bg="#ffffff", anchor="w").pack(fill="x", pady=(6, 2))
            var = tk.StringVar(value=default)
            tk.Entry(parent, textvariable=var, font=("Segoe UI", 10),
                     relief="flat", bg="#f8f8fc", highlightthickness=1,
                     highlightbackground="#e8e6f0", highlightcolor="#6c5ce7").pack(fill="x")
            return var

        name_var = _field(body, "Name", editing.get("name", ""))
        path_var = _field(body, "Path or URL", editing.get("path", ""))

        tk.Label(body, text="Category", font=("Segoe UI", 9, "bold"),
                 fg="#4a3f6b", bg="#ffffff", anchor="w").pack(fill="x", pady=(6, 2))
        cat_var = tk.StringVar(value=editing.get("category", "External Tools"))
        ttk.Combobox(body, textvariable=cat_var, values=CATEGORIES,
                     state="readonly", font=("Segoe UI", 9)).pack(fill="x")

        btn_row = tk.Frame(dlg, bg="#ffffff", pady=10)
        btn_row.pack(fill="x", padx=20)

        def _save():
            name, path = name_var.get().strip(), path_var.get().strip()
            if not name or not path:
                messagebox.showerror("Missing", "Name and Path are required", parent=dlg)
                return
            externals = load_external_apps()
            for e in externals:
                if e["script"] == editing["script"]:
                    e["name"], e["path"], e["category"] = name, path, cat_var.get()
                    words = name.split()
                    e["icon"] = (words[0][0] + words[1][0]).upper() if len(words) >= 2 else name[:2].upper()
                    break
            save_external_apps(externals)
            dlg.destroy()
            self._rebuild_gallery()

        tk.Button(btn_row, text="Save", font=("Segoe UI", 10, "bold"),
                  fg="#ffffff", bg="#6c5ce7", relief="flat", padx=20, pady=4,
                  cursor="hand2", command=_save).pack(side="right", padx=4)
        tk.Button(btn_row, text="Cancel", font=("Segoe UI", 10),
                  fg="#888", bg="#f0f0f5", relief="flat", padx=14, pady=4,
                  cursor="hand2", command=dlg.destroy).pack(side="right")

    def _choose_thumbnail_method(self, app):
        dlg = self._dialog("Capture Thumbnail", 440, 320)

        tk.Label(dlg, text=f"Thumbnail for {app['name']}",
                 font=("Segoe UI", 13, "bold"), fg="#2d2740", bg="#ffffff", pady=16).pack()
        tk.Label(dlg, text="How should we capture a thumbnail?",
                 font=("Segoe UI", 9), fg="#888", bg="#ffffff").pack()

        btn_frame = tk.Frame(dlg, bg="#ffffff", padx=20, pady=16)
        btn_frame.pack(fill="both", expand=True)

        def make_method_btn(text, desc, cmd, color):
            f = tk.Frame(btn_frame, bg="#ffffff", cursor="hand2")
            f.pack(fill="x", pady=4)
            inner = tk.Frame(f, bg=color, padx=12, pady=10)
            inner.pack(fill="x")
            tk.Label(inner, text=text, font=("Segoe UI", 10, "bold"),
                     fg="#2d2740", bg=color, anchor="w").pack(fill="x")
            tk.Label(inner, text=desc, font=("Segoe UI", 8),
                     fg="#555", bg=color, anchor="w").pack(fill="x")
            for widget in [f, inner] + list(inner.winfo_children()):
                widget.bind("<Button-1>", lambda e: cmd())

        make_method_btn("\U0001f916 Auto",
                        "I'll launch it, wait, screenshot, and kill it. Works for most apps.",
                        lambda: (dlg.destroy(), self._auto_capture_thumbnail(app)), "#e8f5e9")
        make_method_btn("\u270b Manual (human-in-the-loop)",
                        "You launch and position it. Click a button when ready.",
                        lambda: (dlg.destroy(), self._manual_capture_thumbnail(app)), "#fff3e0")
        make_method_btn("\U0001f4c1 Pick image",
                        "Use an existing PNG/JPG from disk.",
                        lambda: (dlg.destroy(), self._pick_thumbnail_file(app)), "#e3f2fd")

        tk.Button(dlg, text="Skip (use placeholder)", font=("Segoe UI", 9),
                  fg="#888", bg="#f0f0f5", relief="flat", padx=16, pady=6,
                  cursor="hand2",
                  command=lambda: (dlg.destroy(), self._rebuild_gallery())).pack(pady=8)

    def _auto_capture_thumbnail(self, app):
        self.status_label.config(text=f"Auto-capturing thumbnail for {app['name']}...")

        def _work():
            thumb_path = self._ext_thumb_path(app)
            path_str = app.get("path", "")
            proc = None
            try:
                proc = _launch_path(path_str)
                time.sleep(4)

                import win32gui
                hwnd = None
                deadline = time.time() + 4
                name_lower = app["name"].lower()
                while time.time() < deadline:
                    found = []
                    def cb(h, _):
                        if win32gui.IsWindowVisible(h):
                            t = win32gui.GetWindowText(h)
                            if t and name_lower in t.lower() and "Gallery" not in t:
                                found.append((h, t))
                        return True
                    try: win32gui.EnumWindows(cb, None)
                    except: pass
                    if found:
                        hwnd = found[0][0]
                        break
                    time.sleep(0.5)

                if hwnd:
                    try: win32gui.SetForegroundWindow(hwnd)
                    except: pass
                    time.sleep(0.4)
                    x1, y1, x2, y2 = win32gui.GetWindowRect(hwnd)
                    w, h = x2 - x1, y2 - y1
                    if w >= 40 and h >= 40:
                        with mss.mss() as sct:
                            region = {"left": max(0, x1 - 6), "top": max(0, y1 - 6),
                                       "width": w + 12, "height": h + 12}
                            shot = sct.grab(region)
                            img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
                            img.resize((504, 284), Image.LANCZOS).save(str(thumb_path), quality=92)
                        self._save_thumb_path(app, thumb_path)
                        self.status_label.config(text=f"\u2713 Captured thumbnail for {app['name']}")
                    else:
                        self.status_label.config(text="Window too small -- try manual mode")
                else:
                    self.status_label.config(text="Couldn't find window -- please use manual mode")
                    self.root.after(100, lambda: self._manual_capture_thumbnail(app))
                    return
            except Exception as e:
                self.status_label.config(text=f"Auto-capture failed: {e}")
            finally:
                if proc:
                    try: proc.kill()
                    except: pass
            self.root.after(100, self._rebuild_gallery)

        threading.Thread(target=_work, daemon=True).start()

    def _manual_capture_thumbnail(self, app):
        dlg = self._dialog("Manual Capture", 460, 340, geometry="460x340+40+40")

        tk.Label(dlg, text=f"Manual Capture: {app['name']}",
                 font=("Segoe UI", 13, "bold"), fg="#2d2740", bg="#ffffff", pady=14).pack()

        instructions = tk.Frame(dlg, bg="#fff3e0", padx=16, pady=12)
        instructions.pack(fill="x", padx=16, pady=4)
        tk.Label(instructions, text="STEP-BY-STEP",
                 font=("Segoe UI", 8, "bold"), fg="#e65100", bg="#fff3e0", anchor="w").pack(fill="x")
        tk.Label(instructions,
                 text="1. Click 'Launch App' below\n"
                      "2. Wait for your app's window to appear\n"
                      "3. Position and resize it nicely\n"
                      "4. Click 'Capture Active Window' -- this dialog stays out of the way",
                 font=("Segoe UI", 9), fg="#555", bg="#fff3e0",
                 justify="left", anchor="w").pack(fill="x", pady=4)

        def _launch():
            try:
                _launch_path(app.get("path", ""))
                launch_btn.config(text="\u2713 Launched -- now position your window", bg="#a6e3a1")
            except Exception as e:
                messagebox.showerror("Launch failed", str(e), parent=dlg)

        launch_btn = tk.Button(dlg, text="\u25b6 Launch App",
                    font=("Segoe UI", 11, "bold"), fg="#ffffff", bg="#6c5ce7",
                    relief="flat", padx=20, pady=8, cursor="hand2", command=_launch)
        launch_btn.pack(pady=(10, 6))

        def _capture():
            dlg.withdraw()
            self.root.withdraw()
            time.sleep(0.8)
            try:
                import win32gui
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd)
                if not hwnd or "Gallery" in title or "Capture" in title:
                    messagebox.showwarning("Wrong window",
                        "The active window looks like the Gallery itself. Click on your target app first, then capture.",
                        parent=self.root)
                    dlg.deiconify(); self.root.deiconify()
                    return
                x1, y1, x2, y2 = win32gui.GetWindowRect(hwnd)
                w_, h_ = x2 - x1, y2 - y1
                if w_ < 40 or h_ < 40:
                    messagebox.showwarning("Too small", f"Window is only {w_}x{h_}. Make it bigger.", parent=self.root)
                    dlg.deiconify(); self.root.deiconify()
                    return
                thumb_path = self._ext_thumb_path(app)
                with mss.mss() as sct:
                    region = {"left": max(0, x1 - 6), "top": max(0, y1 - 6),
                              "width": w_ + 12, "height": h_ + 12}
                    shot = sct.grab(region)
                    img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
                    img.resize((504, 284), Image.LANCZOS).save(str(thumb_path), quality=92)
                self._save_thumb_path(app, thumb_path)
                self.root.deiconify()
                dlg.destroy()
                self.status_label.config(text=f"\u2713 Captured '{title[:30]}' for {app['name']}")
                self._rebuild_gallery()
            except Exception as e:
                self.root.deiconify(); dlg.deiconify()
                messagebox.showerror("Capture failed", str(e), parent=dlg)

        tk.Button(dlg, text="\U0001f4f8 Capture Active Window",
                    font=("Segoe UI", 11, "bold"), fg="#ffffff", bg="#f5c2e7",
                    relief="flat", padx=20, pady=8, cursor="hand2", command=_capture).pack(pady=6)
        tk.Button(dlg, text="Cancel", font=("Segoe UI", 9),
                    fg="#888", bg="#f0f0f5", relief="flat", padx=14, pady=4,
                    cursor="hand2",
                    command=lambda: (dlg.destroy(), self._rebuild_gallery())).pack(pady=4)

    def _pick_thumbnail_file(self, app):
        filepath = filedialog.askopenfilename(
            parent=self.root, title="Choose thumbnail image",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp"), ("All files", "*.*")])
        if not filepath:
            self._rebuild_gallery()
            return
        try:
            thumb_path = self._ext_thumb_path(app)
            Image.open(filepath).convert("RGB").resize((504, 284), Image.LANCZOS).save(str(thumb_path), quality=92)
            self._save_thumb_path(app, thumb_path)
            self.status_label.config(text=f"\u2713 Thumbnail set from file for {app['name']}")
        except Exception as e:
            messagebox.showerror("Image error", str(e), parent=self.root)
        self._rebuild_gallery()

    def _delete_external(self, app):
        if not messagebox.askyesno("Delete", f"Remove '{app['name']}' from your gallery?", parent=self.root):
            return
        externals = [e for e in load_external_apps() if e["script"] != app["script"]]
        save_external_apps(externals)
        self._rebuild_gallery()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    GalleryLauncher().run()
