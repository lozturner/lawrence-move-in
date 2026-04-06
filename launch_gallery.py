"""
Lawrence: Move In — Level 4: Gallery Launcher v1.0.0
Visual gallery of every applet with live thumbnails, descriptions, and checkboxes.
Spins each app up briefly to capture a screenshot, then presents the full catalogue.

Usage:
  python launch_gallery.py
  python launch_level.py 4
"""
__version__ = "1.0.0"
import selfclean; selfclean.ensure_single("launch_gallery.py")

import json, os, subprocess, sys, time, threading, tkinter as tk
from tkinter import ttk
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter
import mss, mss.tools

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHONW    = Path(sys.executable).with_name("pythonw.exe")
DETACHED   = 0x00000008
THUMB_DIR  = SCRIPT_DIR / "thumbnails"
THUMB_DIR.mkdir(exist_ok=True)

# ── App catalogue — every app with its story ─────────────────────────────────
APPS = [
    {
        "script": "hot_corner.py",
        "name": "Hot Corners",
        "icon": "HC", "color": "#a6e3a1", "level": 1,
        "problem": "Windows has no hot corners. Mac does. You want screen corner triggers.",
        "solution": "Move your mouse to any corner — triggers actions. Alt+Tab, Task View, Telegram, or run any file you pick.",
        "category": "Window Management",
    },
    {
        "script": "niggly.py",
        "name": "Focus Rules",
        "icon": "NM", "color": "#a6e3a1", "level": 1,
        "problem": "Focus one window, lose three others. No concept of window pairing.",
        "solution": "IF/THEN cards: 'When I focus VS Code, minimise Chrome.' Polls every 150ms, enforces silently.",
        "category": "Window Management",
    },
    {
        "script": "tiles.py",
        "name": "Window Tiles",
        "icon": "TL", "color": "#94e2d5", "level": 1,
        "problem": "No visual map of what's open. Taskbar shows tiny useless icons.",
        "solution": "Every window as a coloured tile, grouped by type. Desktop canvas mode with passthrough ghost overlay.",
        "category": "Window Management",
    },
    {
        "script": "app_tray.py",
        "name": "App Tray",
        "icon": "AT", "color": "#89b4fa", "level": 1,
        "problem": "Your most-used apps have no permanent tray icons with real logos.",
        "solution": "Real icons extracted from .exe files sitting in your system tray. One right-click to open.",
        "category": "Window Management",
    },
    {
        "script": "nag.py",
        "name": "Nag",
        "icon": "NG", "color": "#f9e2af", "level": 1,
        "problem": "You forget what you should be doing. No timetable nagger exists.",
        "solution": "Pops up every 5 minutes: 'Hey, it's 14:30. You should be doing X.' Linked to Google Calendar.",
        "category": "Productivity",
    },
    {
        "script": "hub.py",
        "name": "Hub",
        "icon": "HB", "color": "#b4befe", "level": 2,
        "problem": "Too many applets, no single place to see or launch them.",
        "solution": "Steam Deck-style tile grid. Green dot = running. Click to launch. Triple-click to hard reset.",
        "category": "Productivity",
    },
    {
        "script": "linker.py",
        "name": "Linker",
        "icon": "LK", "color": "#b4befe", "level": 2,
        "problem": "You use the same connector phrases but can never find them mid-thought.",
        "solution": "Clickable phrase tiles. Multi-select, zoom, AI auto-suggest from screenshot. Click = clipboard.",
        "category": "Productivity",
    },
    {
        "script": "mouse_pause.py",
        "name": "Mouse Pause",
        "icon": "MP", "color": "#f5c2e7", "level": 2,
        "problem": "You sit back. The computer doesn't notice. No bridge to 'what next?'",
        "solution": "Detects idle mouse. Action panel pops up. Hands-free voice, AI input, custom tiles. Click to lock.",
        "category": "AI & Voice",
    },
    {
        "script": "scribe.py",
        "name": "Scribe",
        "icon": "SC", "color": "#89dceb", "level": 2,
        "problem": "Ideas flow when you speak. But STT is buried in menus and needs internet.",
        "solution": "Floating always-on speech-to-text. Offline Vosk. Auto-tags content. Copy anywhere.",
        "category": "AI & Voice",
    },
    {
        "script": "voicesort.py",
        "name": "Voice Sort",
        "icon": "VS", "color": "#fab387", "level": 2,
        "problem": "Thoughts vanish. Clipboard copies disappear. Nothing gets categorised.",
        "solution": "Catches every Ctrl+C. Claude sorts into thought/task/idea/rant. Files to markdown automatically.",
        "category": "AI & Voice",
    },
    {
        "script": "kidlin.py",
        "name": "Kidlin's Law",
        "icon": "KL", "color": "#f9e2af", "level": 2,
        "problem": "You can't articulate the actual problem. ADHD brain tangles everything.",
        "solution": "Type messy thinking. Claude returns: 'The actual problem is...' — clean, actionable, shareable.",
        "category": "AI & Voice",
    },
    {
        "script": "watcher.py",
        "name": "Watcher",
        "icon": "WA", "color": "#89b4fa", "level": 3,
        "problem": "You zone out and forget what you were doing. Nobody's watching.",
        "solution": "Mouse stops 3 seconds → screenshot → Claude Vision reads what's on screen and tells you.",
        "category": "AI & Voice",
    },
    {
        "script": "nacho.py",
        "name": "NACHO",
        "icon": "NA", "color": "#cba6f7", "level": 3,
        "problem": "No one to talk to when you're stuck. Typing into ChatGPT is too slow.",
        "solution": "Voice AI. Speaks to you by name. You talk, it listens. Every sentence is a clickable hyperlink.",
        "category": "AI & Voice",
    },
    {
        "script": "replay.py",
        "name": "Replay",
        "icon": "RP", "color": "#89b4fa", "level": 3,
        "problem": "Can't remember what you did an hour ago. No record, no trail, no proof.",
        "solution": "Screenshots every 10s. Mouse trail. Window log. Clipboard. Scrub timeline. Export report.",
        "category": "Session Management",
    },
    {
        "script": "capture.py",
        "name": "Capture",
        "icon": "CP", "color": "#fab387", "level": 3,
        "problem": "You need to brain-dump a screenshot + notes but there's no quick tool.",
        "solution": "Click tray → screenshot + notes popup. Sessions bundle captures. AI processes on export.",
        "category": "Session Management",
    },
    {
        "script": "winddown.py",
        "name": "Winddown",
        "icon": "WD", "color": "#94e2d5", "level": 3,
        "problem": "You don't know how to walk away. Nothing verifies you're done.",
        "solution": "Scans everything open. Auto-checklist. AI verifies loose ends. Saves state. Resumes next day.",
        "category": "Session Management",
    },
    {
        "script": "annoyances.py",
        "name": "Annoyances",
        "icon": "AN", "color": "#f38ba8", "level": 3,
        "problem": "Computer annoyances pile up. You grumble and forget. Never logged, never fixed.",
        "solution": "Persistent checklist. Text/voice/screenshot input. AI suggests workarounds. Exports to markdown.",
        "category": "Session Management",
    },
    {
        "script": "launcher.py",
        "name": "Master Launcher",
        "icon": "MI", "color": "#cba6f7", "level": 3,
        "problem": "No motivation to use your own tools. No feedback loop.",
        "solution": "Gamification. Glowing orbs. XP ring. Level up by using your suite. Progress bars and unlocks.",
        "category": "Session Management",
    },
]

CATEGORIES = ["Window Management", "Productivity", "AI & Voice", "Session Management"]
CAT_COLORS = {
    "Window Management": "#a6e3a1",
    "Productivity": "#b4befe",
    "AI & Voice": "#89b4fa",
    "Session Management": "#94e2d5",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_running():
    import psutil
    running = set()
    for p in psutil.process_iter(["pid","name","cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
            if len(cmd)>1 and "niggly_machine" in cmd[1] and "python" in (p.info["name"] or "").lower():
                running.add(os.path.basename(cmd[1]))
        except: pass
    return running

def kill_all_suite():
    import psutil
    my = os.getpid()
    for p in psutil.process_iter(["pid","name","cmdline"]):
        if p.info["pid"] == my: continue
        try:
            cmd = p.info["cmdline"] or []
            if len(cmd)>1 and "niggly_machine" in cmd[1] and "python" in (p.info["name"] or "").lower():
                p.kill()
        except: pass

def take_desktop_screenshot():
    """Capture the full desktop as a PIL Image."""
    with mss.mss() as sct:
        mon = sct.monitors[0]  # full virtual screen
        shot = sct.grab(mon)
        return Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)

def make_placeholder_thumb(app, size=(280, 160)):
    """Generate a styled placeholder thumbnail for an app."""
    w, h = size
    img = Image.new("RGB", (w, h), "#1e1e2e")
    draw = ImageDraw.Draw(img)
    # Gradient-ish background
    col = app["color"]
    r, g, b = int(col[1:3],16), int(col[3:5],16), int(col[5:7],16)
    for y in range(h):
        f = y / h * 0.3
        draw.line([(0,y),(w,y)], fill=(int(r*f), int(g*f), int(b*f)))
    # Icon circle
    cx, cy = w//2, h//2 - 10
    r_circle = 30
    draw.ellipse([cx-r_circle, cy-r_circle, cx+r_circle, cy+r_circle],
                 fill=col, outline=col)
    try:
        font = ImageFont.truetype("consola.ttf", 20)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0,0), app["icon"], font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    draw.text((cx - tw//2, cy - th//2), app["icon"], fill="#1e1e2e", font=font)
    # Name
    try:
        name_font = ImageFont.truetype("segoeui.ttf", 14)
    except:
        name_font = font
    bbox2 = draw.textbbox((0,0), app["name"], font=name_font)
    tw2 = bbox2[2] - bbox2[0]
    draw.text((cx - tw2//2, cy + r_circle + 10), app["name"], fill="#cdd6f4", font=name_font)
    return img

def capture_app_thumbnail(app, timeout=4):
    """Try to launch app, screenshot it, kill it, return thumbnail path."""
    thumb_path = THUMB_DIR / f"{app['script'].replace('.py','')}.png"
    # If we already have a cached thumbnail less than 1 hour old, reuse it
    if thumb_path.exists():
        age = time.time() - thumb_path.stat().st_mtime
        if age < 3600:
            return thumb_path

    script_path = SCRIPT_DIR / app["script"]
    if not script_path.exists():
        # Generate placeholder
        img = make_placeholder_thumb(app)
        img.save(str(thumb_path))
        return thumb_path

    try:
        # Launch the app
        proc = subprocess.Popen(
            [str(PYTHONW), str(script_path)],
            creationflags=DETACHED, cwd=str(SCRIPT_DIR)
        )
        # Wait for it to create a window
        time.sleep(timeout)
        # Screenshot the desktop
        desktop = take_desktop_screenshot()
        # Crop to a reasonable area and resize as thumbnail
        sw, sh = desktop.size
        # Take centre portion
        thumb = desktop.resize((280, 160), Image.LANCZOS)
        thumb.save(str(thumb_path))
        # Kill the app
        try: proc.kill()
        except: pass
        return thumb_path
    except Exception as e:
        # Fallback to placeholder
        img = make_placeholder_thumb(app)
        img.save(str(thumb_path))
        return thumb_path

# ── Gallery Window ────────────────────────────────────────────────────────────
class GalleryLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Lawrence: Move In — Level 4 Gallery v1.0.0")
        self.root.configure(bg="#f8f8fc")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = min(1100, sw - 80), min(820, sh - 80)
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.root.minsize(700, 500)

        self.checks = {}       # script -> BooleanVar
        self.thumb_imgs = {}   # script -> ImageTk.PhotoImage (prevent GC)
        self.thumb_labels = {} # script -> Label widget
        self._running = set()

        self._build_ui()
        self._load_thumbnails_async()
        self._poll_running()

    def _build_ui(self):
        root = self.root

        # ── Header ──
        hdr = tk.Frame(root, bg="#ffffff", padx=20, pady=16)
        hdr.pack(fill="x")

        tk.Label(hdr, text="Lawrence: Move In",
                 font=("Segoe UI", 22, "bold"), fg="#4a3f6b", bg="#ffffff").pack(side="left")

        tk.Label(hdr, text="Level 4 — Full Gallery",
                 font=("Segoe UI", 12), fg="#8b82a8", bg="#ffffff", padx=16).pack(side="left")

        # Right side buttons
        btn_frame = tk.Frame(hdr, bg="#ffffff")
        btn_frame.pack(side="right")

        self.run_btn = tk.Button(btn_frame, text="▶  Run Selected",
                    font=("Segoe UI", 11, "bold"), fg="#ffffff", bg="#6c5ce7",
                    activeforeground="#ffffff", activebackground="#5a4bd1",
                    relief="flat", padx=20, pady=6, cursor="hand2",
                    command=self._run_selected)
        self.run_btn.pack(side="right", padx=(8,0))

        tk.Button(btn_frame, text="Select All",
                  font=("Segoe UI", 9), fg="#6c5ce7", bg="#f0eef8",
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._select_all).pack(side="right", padx=4)

        tk.Button(btn_frame, text="Clear",
                  font=("Segoe UI", 9), fg="#888", bg="#f0f0f5",
                  relief="flat", padx=12, pady=4, cursor="hand2",
                  command=self._clear_all).pack(side="right", padx=4)

        # ── Divider ──
        tk.Frame(root, bg="#e8e6f0", height=2).pack(fill="x")

        # ── Status bar ──
        self.status_frame = tk.Frame(root, bg="#faf9ff", padx=20, pady=8)
        self.status_frame.pack(fill="x")
        self.status_label = tk.Label(self.status_frame, text="Loading thumbnails...",
                                      font=("Segoe UI", 9), fg="#8b82a8", bg="#faf9ff")
        self.status_label.pack(side="left")
        self.count_label = tk.Label(self.status_frame, text="0 selected",
                                     font=("Segoe UI", 9, "bold"), fg="#6c5ce7", bg="#faf9ff")
        self.count_label.pack(side="right")

        # ── Scrollable gallery ──
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

        # Mouse wheel
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self._canvas = canvas

        # ── Build cards by category ──
        for cat in CATEGORIES:
            cat_apps = [a for a in APPS if a["category"] == cat]
            if not cat_apps:
                continue

            cat_color = CAT_COLORS.get(cat, "#888")

            # Category header
            cat_frame = tk.Frame(self.scroll_frame, bg="#f8f8fc")
            cat_frame.pack(fill="x", padx=20, pady=(20, 4))

            # Coloured dot + category name
            dot = tk.Canvas(cat_frame, width=12, height=12, bg="#f8f8fc", highlightthickness=0)
            dot.create_oval(2, 2, 10, 10, fill=cat_color, outline=cat_color)
            dot.pack(side="left", padx=(0, 8))

            tk.Label(cat_frame, text=cat.upper(),
                     font=("Segoe UI", 10, "bold"), fg="#4a3f6b",
                     bg="#f8f8fc", anchor="w").pack(side="left")

            tk.Label(cat_frame, text=f"{len(cat_apps)} apps",
                     font=("Segoe UI", 9), fg="#aaa",
                     bg="#f8f8fc").pack(side="left", padx=8)

            # Thin accent line
            accent = tk.Frame(self.scroll_frame, bg=cat_color, height=2)
            accent.pack(fill="x", padx=20, pady=(0, 8))

            # Cards grid
            grid_frame = tk.Frame(self.scroll_frame, bg="#f8f8fc")
            grid_frame.pack(fill="x", padx=16)

            for i, app in enumerate(cat_apps):
                self._make_card(grid_frame, app, i)

        # ── Footer ──
        footer = tk.Frame(self.scroll_frame, bg="#f8f8fc", pady=16)
        footer.pack(fill="x", padx=20)
        tk.Label(footer, text="Level 4 loads the full gallery. Select what you need, hit Run.",
                 font=("Segoe UI", 9), fg="#aaa", bg="#f8f8fc").pack()
        tk.Label(footer, text="Built by Loz Turner · 2026 · Lawrence: Move In",
                 font=("Segoe UI", 8), fg="#ccc", bg="#f8f8fc").pack()

    def _make_card(self, parent, app, index):
        """Create a single app card with thumbnail, checkbox, descriptions."""
        col = app["color"]
        script = app["script"]

        # Card frame
        card = tk.Frame(parent, bg="#ffffff", padx=0, pady=0,
                        relief="flat", highlightthickness=1,
                        highlightbackground="#e8e6f0")
        card.grid(row=index // 3, column=index % 3, padx=8, pady=8, sticky="nsew")
        parent.grid_columnconfigure(index % 3, weight=1)

        # Coloured top accent
        tk.Frame(card, bg=col, height=4).pack(fill="x")

        inner = tk.Frame(card, bg="#ffffff", padx=14, pady=10)
        inner.pack(fill="both", expand=True)

        # ── Top row: checkbox + name + level badge ──
        top = tk.Frame(inner, bg="#ffffff")
        top.pack(fill="x")

        var = tk.BooleanVar(value=False)
        self.checks[script] = var

        cb = tk.Checkbutton(top, variable=var, bg="#ffffff", activebackground="#ffffff",
                            selectcolor="#ffffff", command=self._update_count)
        cb.pack(side="left")

        tk.Label(top, text=app["name"],
                 font=("Segoe UI", 11, "bold"), fg="#2d2740",
                 bg="#ffffff").pack(side="left", padx=(4,0))

        # Level badge
        level_colors = {1: "#a6e3a1", 2: "#89b4fa", 3: "#cba6f7"}
        badge_bg = level_colors.get(app["level"], "#888")
        badge = tk.Label(top, text=f" L{app['level']} ",
                         font=("Consolas", 8, "bold"), fg="#1e1e2e",
                         bg=badge_bg)
        badge.pack(side="right")

        # Status dot
        self._status_dot_canvas = {}
        dot_c = tk.Canvas(top, width=10, height=10, bg="#ffffff", highlightthickness=0)
        dot_c.pack(side="right", padx=4)
        self._status_dot_canvas[script] = dot_c

        # ── Thumbnail ──
        thumb_frame = tk.Frame(inner, bg="#e8e6f0", width=252, height=142)
        thumb_frame.pack(fill="x", pady=(8,6))
        thumb_frame.pack_propagate(False)

        thumb_label = tk.Label(thumb_frame, bg="#e8e6f0", text="Loading...",
                               font=("Segoe UI", 9), fg="#aaa")
        thumb_label.pack(expand=True)
        self.thumb_labels[script] = thumb_label

        # ── Problem ──
        prob_frame = tk.Frame(inner, bg="#fff5f5", padx=8, pady=6)
        prob_frame.pack(fill="x", pady=(4,2))
        tk.Label(prob_frame, text="THE PROBLEM", font=("Segoe UI", 7, "bold"),
                 fg="#e64553", bg="#fff5f5", anchor="w").pack(fill="x")
        tk.Label(prob_frame, text=app["problem"],
                 font=("Segoe UI", 8), fg="#6e5a5a", bg="#fff5f5",
                 wraplength=220, justify="left", anchor="w").pack(fill="x")

        # ── Solution ──
        r, g, b = int(col[1:3],16), int(col[3:5],16), int(col[5:7],16)
        sol_bg = f"#{min(r+220,255):02x}{min(g+220,255):02x}{min(b+220,255):02x}"
        sol_frame = tk.Frame(inner, bg=sol_bg, padx=8, pady=6)
        sol_frame.pack(fill="x", pady=(2,4))
        tk.Label(sol_frame, text="THE SOLUTION", font=("Segoe UI", 7, "bold"),
                 fg=col, bg=sol_bg, anchor="w").pack(fill="x")
        tk.Label(sol_frame, text=app["solution"],
                 font=("Segoe UI", 8), fg="#3a3a4a", bg=sol_bg,
                 wraplength=220, justify="left", anchor="w").pack(fill="x")

        # ── Script name ──
        tk.Label(inner, text=f"{app['script']}",
                 font=("Consolas", 8), fg="#aaa", bg="#ffffff", anchor="w").pack(fill="x")

        # Click card to toggle checkbox
        def _toggle(e, v=var):
            v.set(not v.get())
            self._update_count()
        for w in [card, inner, thumb_frame]:
            w.bind("<Button-1>", _toggle)

    def _update_count(self):
        n = sum(1 for v in self.checks.values() if v.get())
        self.count_label.config(text=f"{n} selected")
        if n > 0:
            self.run_btn.config(text=f"▶  Run {n} App{'s' if n>1 else ''}", bg="#6c5ce7")
        else:
            self.run_btn.config(text="▶  Run Selected", bg="#a8a0c0")

    def _select_all(self):
        for v in self.checks.values():
            v.set(True)
        self._update_count()

    def _clear_all(self):
        for v in self.checks.values():
            v.set(False)
        self._update_count()

    def _run_selected(self):
        selected = [s for s, v in self.checks.items() if v.get()]
        if not selected:
            self.status_label.config(text="Nothing selected — tick the apps you want to run")
            return

        kill_all_suite()
        time.sleep(0.5)

        launched = 0
        for app in APPS:
            if app["script"] in selected:
                path = SCRIPT_DIR / app["script"]
                if path.exists():
                    subprocess.Popen([str(PYTHONW), str(path)],
                                     creationflags=DETACHED, cwd=str(SCRIPT_DIR))
                    launched += 1
                    time.sleep(0.3)

        self.status_label.config(text=f"Launched {launched} apps")
        self._update_count()

    def _load_thumbnails_async(self):
        """Load cached thumbnails or generate placeholders. No live capture (too disruptive)."""
        def _load():
            for app in APPS:
                script = app["script"]
                thumb_path = THUMB_DIR / f"{script.replace('.py','')}.png"

                # Generate placeholder if no cached thumbnail
                if not thumb_path.exists():
                    img = make_placeholder_thumb(app, size=(252, 142))
                    img.save(str(thumb_path))

                try:
                    img = Image.open(str(thumb_path))
                    img = img.resize((252, 142), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.thumb_imgs[script] = photo

                    if script in self.thumb_labels:
                        lbl = self.thumb_labels[script]
                        try:
                            lbl.config(image=photo, text="")
                        except tk.TclError:
                            pass
                except Exception:
                    pass

            try:
                self.status_label.config(text="Gallery ready — select apps and hit Run")
            except tk.TclError:
                pass

        threading.Thread(target=_load, daemon=True).start()

    def _poll_running(self):
        """Update status dots every 3 seconds."""
        try:
            self._running = get_running()
            for script, dot_c in self._status_dot_canvas.items():
                try:
                    dot_c.delete("all")
                    if script in self._running:
                        dot_c.create_oval(1, 1, 9, 9, fill="#00b894", outline="#00b894")
                    else:
                        dot_c.create_oval(1, 1, 9, 9, fill="#ddd", outline="#ddd")
                except tk.TclError:
                    pass

            running_count = len(self._running)
            cur = self.status_label.cget("text")
            if "Gallery ready" in cur or "running" in cur:
                self.status_label.config(
                    text=f"Gallery ready — {running_count} apps currently running")

            self.root.after(3000, self._poll_running)
        except tk.TclError:
            pass

    def _capture_thumbnails_live(self):
        """Optional: capture real thumbnails by spinning up each app."""
        self.status_label.config(text="Capturing live thumbnails... this takes ~1 minute")

        def _capture():
            for i, app in enumerate(APPS):
                script = app["script"]
                try:
                    self.status_label.config(
                        text=f"Capturing {app['name']}... ({i+1}/{len(APPS)})")
                except tk.TclError:
                    return

                thumb_path = capture_app_thumbnail(app, timeout=3)

                try:
                    img = Image.open(str(thumb_path))
                    img = img.resize((252, 142), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.thumb_imgs[script] = photo

                    if script in self.thumb_labels:
                        self.thumb_labels[script].config(image=photo, text="")
                except Exception:
                    pass

            try:
                self.status_label.config(text="All thumbnails captured")
            except tk.TclError:
                pass

        threading.Thread(target=_capture, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    GalleryLauncher().run()
