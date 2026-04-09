"""
Lawrence: Move In — Level 4: Gallery Launcher v2.0.0
Visual gallery of every applet. Click any card to launch it instantly.
"Launch All" fires everything. "+ Add App" is one paste, one Enter.

Usage:
  python launch_gallery.py
  python launch_level.py 4
"""
__version__ = "2.0.0"
import selfclean; selfclean.ensure_single("launch_gallery.py")

import json, os, subprocess, sys, time, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter
import mss, mss.tools

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHONW    = Path(sys.executable).with_name("pythonw.exe")
DETACHED   = 0x00000008
THUMB_DIR  = SCRIPT_DIR / "thumbnails"
THUMB_DIR.mkdir(exist_ok=True)
EXTERNAL_CONFIG = SCRIPT_DIR / "external_apps.json"

# Default colours for external apps (cycled through when adding)
EXTERNAL_COLORS = ["#f5c2e7", "#89dceb", "#fab387", "#f9e2af", "#a6e3a1",
                    "#b4befe", "#cba6f7", "#94e2d5", "#89b4fa", "#f38ba8"]

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
    {
        "script": "aitimer.py",
        "name": "AI Timer",
        "icon": "AT", "color": "#f9e2af", "level": 2,
        "problem": "You open 4 LLM chats, scatter between them, lose track of time and which ones are done.",
        "solution": "Multiple concurrent timers. Auto-detects AI windows. Periodic check-in popups. Jump-back button to return to any tracked window. Exports time log.",
        "category": "Productivity",
    },
    {
        "script": "steps.py",
        "name": "Steps Recorder",
        "icon": "ST", "color": "#f5c2e7", "level": 3,
        "problem": "Windows Steps Recorder is dead. You need to document what you clicked and why.",
        "solution": "Records every click, keystroke, window switch with screenshots, handles, PIDs, clipboard. Navigable step-by-step viewer. Exports to JSON and markdown.",
        "category": "Session Management",
    },
]

CATEGORIES = ["Window Management", "Productivity", "AI & Voice", "Session Management", "External Tools"]
CAT_COLORS = {
    "Window Management": "#a6e3a1",
    "Productivity": "#b4befe",
    "AI & Voice": "#89b4fa",
    "Session Management": "#94e2d5",
    "External Tools": "#f5c2e7",
}

# ── External apps persistence ─────────────────────────────────────────────────
def load_external_apps():
    """Load user-added external apps from JSON config."""
    if not EXTERNAL_CONFIG.exists():
        return []
    try:
        with open(EXTERNAL_CONFIG, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("apps", [])
    except Exception:
        return []

def save_external_apps(apps):
    """Save user-added external apps to JSON config."""
    try:
        with open(EXTERNAL_CONFIG, "w", encoding="utf-8") as f:
            json.dump({"apps": apps, "version": "1.0"}, f, indent=2)
        return True
    except Exception as e:
        print(f"Save error: {e}")
        return False

def get_all_apps():
    """Return built-in apps + external apps merged."""
    externals = load_external_apps()
    return APPS + externals

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
        self.root.title(f"Lawrence: Move In — Level 4 Gallery v{__version__}")
        self.root.configure(bg="#f8f8fc")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = min(1100, sw - 80), min(820, sh - 80)
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.root.minsize(700, 500)

        self.thumb_imgs = {}   # script -> ImageTk.PhotoImage (prevent GC)
        self.thumb_labels = {} # script -> Label widget
        self._status_dot_canvas = {}
        self._running = set()
        self._app_lookup = {}  # script -> app dict for click-to-launch

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

        self.run_btn = tk.Button(btn_frame, text="▶  Launch All",
                    font=("Segoe UI", 11, "bold"), fg="#ffffff", bg="#6c5ce7",
                    activeforeground="#ffffff", activebackground="#5a4bd1",
                    relief="flat", padx=20, pady=6, cursor="hand2",
                    command=self._launch_all)
        self.run_btn.pack(side="right", padx=(8,0))

        tk.Button(btn_frame, text="+ Add App",
                  font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#f5c2e7",
                  activeforeground="#ffffff", activebackground="#e8a7d4",
                  relief="flat", padx=14, pady=6, cursor="hand2",
                  command=self._show_add_dialog).pack(side="right", padx=(4,8))

        # ── Divider ──
        tk.Frame(root, bg="#e8e6f0", height=2).pack(fill="x")

        # ── Status bar ──
        self.status_frame = tk.Frame(root, bg="#faf9ff", padx=20, pady=8)
        self.status_frame.pack(fill="x")
        self.status_label = tk.Label(self.status_frame, text="Loading thumbnails...",
                                      font=("Segoe UI", 9), fg="#8b82a8", bg="#faf9ff")
        self.status_label.pack(side="left")
        self.count_label = tk.Label(self.status_frame, text="0 running",
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
        all_apps = get_all_apps()
        self._all_apps_cache = all_apps
        for cat in CATEGORIES:
            cat_apps = [a for a in all_apps if a.get("category") == cat]
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
        tk.Label(footer, text="Click any card to launch it. 'Launch All' fires everything.",
                 font=("Segoe UI", 9), fg="#aaa", bg="#f8f8fc").pack()
        tk.Label(footer, text="Built by Loz Turner · 2026 · Lawrence: Move In",
                 font=("Segoe UI", 8), fg="#ccc", bg="#f8f8fc").pack()

    def _make_card(self, parent, app, index):
        """Create a single app card. Click anywhere on it to launch immediately."""
        col = app["color"]
        script = app["script"]
        self._app_lookup[script] = app

        # Card frame
        card = tk.Frame(parent, bg="#ffffff", padx=0, pady=0,
                        relief="flat", highlightthickness=1,
                        highlightbackground="#e8e6f0", cursor="hand2")
        card.grid(row=index // 3, column=index % 3, padx=8, pady=8, sticky="nsew")
        parent.grid_columnconfigure(index % 3, weight=1)

        # Coloured top accent
        tk.Frame(card, bg=col, height=4).pack(fill="x")

        inner = tk.Frame(card, bg="#ffffff", padx=14, pady=10, cursor="hand2")
        inner.pack(fill="both", expand=True)

        # ── Top row: name + level badge + status dot ──
        top = tk.Frame(inner, bg="#ffffff")
        top.pack(fill="x")

        tk.Label(top, text=app["name"],
                 font=("Segoe UI", 11, "bold"), fg="#2d2740",
                 bg="#ffffff", cursor="hand2").pack(side="left", padx=(4,0))

        # Level badge or EXT badge
        is_external = app.get("external", False)
        if is_external:
            badge_bg = "#f5c2e7"
            badge_text = " EXT "
        else:
            level_colors = {1: "#a6e3a1", 2: "#89b4fa", 3: "#cba6f7", 4: "#f9e2af"}
            badge_bg = level_colors.get(app["level"], "#888")
            badge_text = f" L{app['level']} "
        badge = tk.Label(top, text=badge_text,
                         font=("Consolas", 8, "bold"), fg="#1e1e2e",
                         bg=badge_bg)
        badge.pack(side="right")

        # Status dot
        dot_c = tk.Canvas(top, width=10, height=10, bg="#ffffff", highlightthickness=0)
        dot_c.pack(side="right", padx=4)
        self._status_dot_canvas[script] = dot_c

        # ── Thumbnail ──
        thumb_frame = tk.Frame(inner, bg="#e8e6f0", width=252, height=142, cursor="hand2")
        thumb_frame.pack(fill="x", pady=(8,6))
        thumb_frame.pack_propagate(False)

        thumb_label = tk.Label(thumb_frame, bg="#e8e6f0", text="Loading...",
                               font=("Segoe UI", 9), fg="#aaa", cursor="hand2")
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

        # ── Script name / path display ──
        if is_external:
            display_path = app.get("path", "")
            if len(display_path) > 42:
                display_path = "..." + display_path[-39:]
            path_text = f"↗ {display_path}"
        else:
            path_text = app['script']
        tk.Label(inner, text=path_text,
                 font=("Consolas", 8), fg="#aaa", bg="#ffffff", anchor="w").pack(fill="x")

        # Single-click anywhere on card = launch this app
        def _click_launch(e, a=app):
            self._launch_single(a)

        # Right-click context menu (Edit/Delete/Recapture for externals)
        def _show_menu(e, a=app):
            menu = tk.Menu(self.root, tearoff=0)
            if a.get("external"):
                menu.add_command(label=f"Launch {a['name']}",
                                 command=lambda: self._launch_single(a))
                menu.add_separator()
                menu.add_command(label="Edit...",
                                 command=lambda: self._edit_external_dialog(a))
                menu.add_command(label="Recapture thumbnail...",
                                 command=lambda: self._choose_thumbnail_method(a))
                menu.add_separator()
                menu.add_command(label="Delete",
                                 command=lambda: self._delete_external(a))
            else:
                menu.add_command(label=f"Launch {a['name']}",
                                 command=lambda: self._launch_single(a))
            try:
                menu.tk_popup(e.x_root, e.y_root)
            finally:
                menu.grab_release()

        # Bind click-to-launch and right-click menu to all card widgets
        for w in [card, inner, thumb_frame, thumb_label]:
            w.bind("<Button-1>", _click_launch)
            w.bind("<Button-3>", _show_menu)

    def _update_running_count(self):
        """Update the running counter label from current poll data."""
        n = len(self._running)
        self.count_label.config(text=f"{n} running")

    def _launch_all(self):
        """Launch every built-in + external app."""
        all_apps = get_all_apps()
        if not all_apps:
            self.status_label.config(text="No apps to launch")
            return

        # Kill existing suite apps first so we get a clean slate
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

    def _load_thumbnails_async(self):
        """Load cached thumbnails or generate placeholders. No live capture (too disruptive)."""
        def _load():
            for app in get_all_apps():
                script = app["script"]
                # External apps use their own thumb_path if set
                if app.get("external") and app.get("thumb_path"):
                    thumb_path = Path(app["thumb_path"])
                else:
                    safe_name = script.replace(".py", "").replace("external:", "ext_").replace(":","_").replace("/","_").replace("\\","_")
                    thumb_path = THUMB_DIR / f"{safe_name}.png"

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
                self.status_label.config(text="Gallery ready — click any card to launch")
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

            self._update_running_count()
            cur = self.status_label.cget("text")
            if "Gallery ready" in cur or "running" in cur:
                self.status_label.config(
                    text=f"Gallery ready — {len(self._running)} apps currently running")

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

    # ── External app management ──────────────────────────────────────────────
    def _rebuild_gallery(self):
        """Tear down scroll_frame contents and rebuild from scratch.
        Called after add/edit/delete of external apps."""
        try:
            # Clear all widgets in scroll_frame
            for child in self.scroll_frame.winfo_children():
                child.destroy()
            # Clear state that references old widgets
            self.thumb_imgs = {}
            self.thumb_labels = {}
            self._status_dot_canvas = {}
            self._app_lookup = {}

            # Rebuild the category sections
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

            # Footer
            footer = tk.Frame(self.scroll_frame, bg="#f8f8fc", pady=16)
            footer.pack(fill="x", padx=20)
            tk.Label(footer, text="Click any card to launch it. 'Launch All' fires everything.",
                     font=("Segoe UI", 9), fg="#aaa", bg="#f8f8fc").pack()
            tk.Label(footer, text="Built by Loz Turner · 2026 · Lawrence: Move In",
                     font=("Segoe UI", 8), fg="#ccc", bg="#f8f8fc").pack()

            # Reload thumbnails
            self._load_thumbnails_async()
            self._update_running_count()
        except tk.TclError:
            pass

    def _show_add_dialog(self, editing=None):
        """Show the add-external-app dialog. If editing is set, pre-fill with that app's data."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Add External App" if not editing else "Edit External App")
        dlg.configure(bg="#ffffff")
        dlg.attributes("-topmost", True)
        dlg.transient(self.root)

        w, h = 560, 640
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # Header
        hdr = tk.Frame(dlg, bg="#f5c2e7", pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="+ Add External App" if not editing else "Edit External App",
                 font=("Segoe UI", 14, "bold"), fg="#2d2740", bg="#f5c2e7").pack()
        tk.Label(hdr, text="Link any .exe, .py, .lnk, .bat, or URL into your gallery",
                 font=("Segoe UI", 9), fg="#6e5a72", bg="#f5c2e7").pack()

        body = tk.Frame(dlg, bg="#ffffff", padx=20, pady=16)
        body.pack(fill="both", expand=True)

        # Helper to build a labelled entry
        def labelled(parent, label, widget):
            tk.Label(parent, text=label, font=("Segoe UI", 9, "bold"),
                     fg="#4a3f6b", bg="#ffffff", anchor="w").pack(fill="x", pady=(8, 2))
            widget.pack(fill="x")
            return widget

        # Name
        name_var = tk.StringVar(value=editing.get("name") if editing else "")
        name_entry = tk.Entry(body, textvariable=name_var, font=("Segoe UI", 10),
                              relief="flat", bg="#f8f8fc", highlightthickness=1,
                              highlightbackground="#e8e6f0", highlightcolor="#6c5ce7")
        labelled(body, "Name", name_entry)

        # Path (with Browse)
        path_frame = tk.Frame(body, bg="#ffffff")
        path_var = tk.StringVar(value=editing.get("path") if editing else "")
        path_entry = tk.Entry(path_frame, textvariable=path_var, font=("Segoe UI", 9),
                              relief="flat", bg="#f8f8fc", highlightthickness=1,
                              highlightbackground="#e8e6f0", highlightcolor="#6c5ce7")
        path_entry.pack(side="left", fill="x", expand=True)

        def _browse():
            filepath = filedialog.askopenfilename(
                parent=dlg, title="Choose app or script",
                filetypes=[("All runnable", "*.exe;*.py;*.lnk;*.bat;*.cmd;*.ps1;*.url"),
                           ("Executables", "*.exe"),
                           ("Python", "*.py"),
                           ("Shortcuts", "*.lnk"),
                           ("Batch", "*.bat;*.cmd"),
                           ("All files", "*.*")])
            if filepath:
                path_var.set(filepath)
                # Auto-fill name if empty
                if not name_var.get():
                    name_var.set(Path(filepath).stem.replace("_", " ").title())

        tk.Button(path_frame, text="Browse…", font=("Segoe UI", 9),
                  bg="#f0eef8", fg="#6c5ce7", relief="flat", padx=12, cursor="hand2",
                  command=_browse).pack(side="left", padx=(6, 0))
        labelled(body, "Path or URL (.exe, .py, .lnk, .bat, https://...)", path_frame)

        # Category
        cat_var = tk.StringVar(value=editing.get("category") if editing else "External Tools")
        cat_combo = ttk.Combobox(body, textvariable=cat_var, values=CATEGORIES,
                                  state="readonly", font=("Segoe UI", 9))
        labelled(body, "Category", cat_combo)

        # Problem
        prob_var = tk.StringVar(value=editing.get("problem") if editing else "")
        prob_entry = tk.Entry(body, textvariable=prob_var, font=("Segoe UI", 9),
                              relief="flat", bg="#fff5f5", highlightthickness=1,
                              highlightbackground="#f5d5d5", highlightcolor="#e64553")
        labelled(body, "The Problem (why do you need this app?)", prob_entry)

        # Solution
        sol_var = tk.StringVar(value=editing.get("solution") if editing else "")
        sol_entry = tk.Entry(body, textvariable=sol_var, font=("Segoe UI", 9),
                              relief="flat", bg="#f5fff7", highlightthickness=1,
                              highlightbackground="#c8e8ce", highlightcolor="#a6e3a1")
        labelled(body, "The Solution (what does it do?)", sol_entry)

        # Icon (2-letter badge)
        icon_var = tk.StringVar(value=editing.get("icon") if editing else "")
        icon_entry = tk.Entry(body, textvariable=icon_var, font=("Consolas", 11, "bold"),
                              relief="flat", bg="#f8f8fc", highlightthickness=1,
                              highlightbackground="#e8e6f0", highlightcolor="#6c5ce7",
                              width=6)
        labelled(body, "Icon (2 letters, e.g. FG for FigJam)", icon_entry)

        # Thumbnail options
        thumb_frame = tk.Frame(body, bg="#faf9ff", padx=10, pady=8)
        thumb_frame.pack(fill="x", pady=(14, 8))
        tk.Label(thumb_frame, text="THUMBNAIL", font=("Segoe UI", 8, "bold"),
                 fg="#6c5ce7", bg="#faf9ff").pack(anchor="w")
        tk.Label(thumb_frame,
                 text="After Save, you'll be asked how to capture the thumbnail:\n"
                      "(1) Auto — I launch it, screenshot, kill it\n"
                      "(2) Manual — you launch it yourself, then click to capture\n"
                      "(3) Pick file — use an existing image on disk",
                 font=("Segoe UI", 8), fg="#666", bg="#faf9ff",
                 justify="left").pack(anchor="w", pady=(4, 0))

        # Buttons
        btn_row = tk.Frame(dlg, bg="#ffffff", pady=14)
        btn_row.pack(fill="x", padx=20)

        def _save():
            name = name_var.get().strip()
            path = path_var.get().strip()
            if not name or not path:
                messagebox.showerror("Missing", "Name and Path are required",
                                     parent=dlg)
                return
            if not editing:
                # Check path exists (unless URL)
                if not path.startswith(("http://", "https://")) and not Path(path).exists():
                    if not messagebox.askyesno("Path not found",
                            f"'{path}' doesn't exist. Save anyway?", parent=dlg):
                        return

            # Build the app dict
            icon = icon_var.get().strip().upper()[:2] or name[:2].upper()
            # Pick colour based on existing count (cycle through)
            externals = load_external_apps()
            if editing:
                color = editing.get("color", EXTERNAL_COLORS[0])
            else:
                color = EXTERNAL_COLORS[len(externals) % len(EXTERNAL_COLORS)]

            # Generate a unique script ID for external apps
            if editing:
                script_id = editing["script"]
            else:
                script_id = f"external:{int(time.time() * 1000)}"

            app = {
                "script": script_id,
                "name": name,
                "path": path,
                "icon": icon,
                "color": color,
                "level": 4,
                "problem": prob_var.get().strip() or "A tool you use that's outside the suite.",
                "solution": sol_var.get().strip() or "One-click launch from the gallery with the rest.",
                "category": cat_var.get(),
                "external": True,
            }

            # Save
            externals = load_external_apps()
            if editing:
                for i, e in enumerate(externals):
                    if e["script"] == editing["script"]:
                        externals[i] = app
                        break
            else:
                externals.append(app)
            save_external_apps(externals)
            dlg.destroy()

            # Now the thumbnail capture flow
            if not editing:
                self._choose_thumbnail_method(app)
            else:
                self._rebuild_gallery()

        def _cancel():
            dlg.destroy()

        tk.Button(btn_row, text="Save", font=("Segoe UI", 10, "bold"),
                  fg="#ffffff", bg="#6c5ce7", relief="flat", padx=24, pady=6,
                  cursor="hand2", command=_save).pack(side="right", padx=4)
        tk.Button(btn_row, text="Cancel", font=("Segoe UI", 10),
                  fg="#888", bg="#f0f0f5", relief="flat", padx=18, pady=6,
                  cursor="hand2", command=_cancel).pack(side="right")

    def _choose_thumbnail_method(self, app):
        """Ask the user how they want to capture the thumbnail for a new external app."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Capture Thumbnail")
        dlg.configure(bg="#ffffff")
        dlg.attributes("-topmost", True)

        w, h = 440, 320
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        tk.Label(dlg, text=f"Thumbnail for {app['name']}",
                 font=("Segoe UI", 13, "bold"), fg="#2d2740", bg="#ffffff",
                 pady=16).pack()
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

        def _auto():
            dlg.destroy()
            self._auto_capture_thumbnail(app)

        def _manual():
            dlg.destroy()
            self._manual_capture_thumbnail(app)

        def _file():
            dlg.destroy()
            self._pick_thumbnail_file(app)

        make_method_btn("🤖 Auto",
                        "I'll launch it, wait, screenshot, and kill it. Works for most apps.",
                        _auto, "#e8f5e9")
        make_method_btn("✋ Manual (human-in-the-loop)",
                        "You launch and position it. Click a button when ready.",
                        _manual, "#fff3e0")
        make_method_btn("📁 Pick image",
                        "Use an existing PNG/JPG from disk.",
                        _file, "#e3f2fd")

        tk.Button(dlg, text="Skip (use placeholder)", font=("Segoe UI", 9),
                  fg="#888", bg="#f0f0f5", relief="flat", padx=16, pady=6,
                  cursor="hand2",
                  command=lambda: (dlg.destroy(), self._rebuild_gallery())).pack(pady=8)

    def _ext_thumb_path(self, app):
        """Return the thumbnail path for an external app."""
        script_id = app["script"]
        safe = script_id.replace("external:", "ext_").replace(":", "_").replace("/","_").replace("\\","_")
        return THUMB_DIR / f"{safe}.png"

    def _auto_capture_thumbnail(self, app):
        """Try to auto-launch the external app, screenshot it, kill it."""
        self.status_label.config(text=f"Auto-capturing thumbnail for {app['name']}...")

        def _work():
            thumb_path = self._ext_thumb_path(app)
            path_str = app.get("path", "")
            p = Path(path_str)

            proc = None
            try:
                if path_str.startswith(("http://", "https://")):
                    os.startfile(path_str)
                elif p.suffix.lower() == ".py":
                    proc = subprocess.Popen([str(PYTHONW), str(p)],
                                             creationflags=DETACHED, cwd=str(p.parent))
                elif p.suffix.lower() in (".lnk", ".url"):
                    os.startfile(str(p))
                elif p.suffix.lower() in (".bat", ".cmd"):
                    proc = subprocess.Popen(["cmd", "/c", str(p)],
                                             creationflags=DETACHED, cwd=str(p.parent))
                else:
                    os.startfile(str(p))

                # Wait for a window to appear
                time.sleep(4)

                # Try to find a window by name substring
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
                    try:
                        win32gui.EnumWindows(cb, None)
                    except:
                        pass
                    if found:
                        hwnd = found[0][0]
                        break
                    time.sleep(0.5)

                if hwnd:
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                    except:
                        pass
                    time.sleep(0.4)
                    rect = win32gui.GetWindowRect(hwnd)
                    x1, y1, x2, y2 = rect
                    w = x2 - x1
                    h = y2 - y1
                    if w >= 40 and h >= 40:
                        with mss.mss() as sct:
                            region = {"left": max(0, x1 - 6), "top": max(0, y1 - 6),
                                       "width": w + 12, "height": h + 12}
                            shot = sct.grab(region)
                            img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
                            img = img.resize((504, 284), Image.LANCZOS)
                            img.save(str(thumb_path), quality=92)

                        # Update app with thumb path
                        externals = load_external_apps()
                        for e in externals:
                            if e["script"] == app["script"]:
                                e["thumb_path"] = str(thumb_path)
                                break
                        save_external_apps(externals)

                        self.status_label.config(text=f"✓ Captured thumbnail for {app['name']}")
                    else:
                        self.status_label.config(text=f"Window too small — try manual mode")
                else:
                    # Fallback: offer manual
                    self.status_label.config(
                        text=f"Couldn't find window — please use manual mode")
                    self.root.after(100, lambda: self._manual_capture_thumbnail(app))
                    return
            except Exception as e:
                self.status_label.config(text=f"Auto-capture failed: {e}")
            finally:
                if proc:
                    try:
                        proc.kill()
                    except:
                        pass

            # Rebuild gallery
            self.root.after(100, self._rebuild_gallery)

        threading.Thread(target=_work, daemon=True).start()

    def _manual_capture_thumbnail(self, app):
        """Human-in-the-loop: let user launch and position the app, then capture."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Manual Capture")
        dlg.configure(bg="#ffffff")
        dlg.attributes("-topmost", True)

        w, h = 460, 340
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"{w}x{h}+40+40")  # top-left so user can position target window

        tk.Label(dlg, text=f"Manual Capture: {app['name']}",
                 font=("Segoe UI", 13, "bold"), fg="#2d2740", bg="#ffffff",
                 pady=14).pack()

        instructions = tk.Frame(dlg, bg="#fff3e0", padx=16, pady=12)
        instructions.pack(fill="x", padx=16, pady=4)
        tk.Label(instructions, text="STEP-BY-STEP",
                 font=("Segoe UI", 8, "bold"), fg="#e65100", bg="#fff3e0",
                 anchor="w").pack(fill="x")
        tk.Label(instructions,
                 text="1. Click 'Launch App' below\n"
                      "2. Wait for your app's window to appear\n"
                      "3. Position and resize it nicely\n"
                      "4. Click 'Capture Active Window' — this dialog stays out of the way",
                 font=("Segoe UI", 9), fg="#555", bg="#fff3e0",
                 justify="left", anchor="w").pack(fill="x", pady=4)

        def _launch():
            path_str = app.get("path", "")
            try:
                p = Path(path_str)
                if path_str.startswith(("http://", "https://")):
                    os.startfile(path_str)
                elif p.suffix.lower() == ".py":
                    subprocess.Popen([str(PYTHONW), str(p)],
                                     creationflags=DETACHED, cwd=str(p.parent))
                elif p.suffix.lower() in (".bat", ".cmd"):
                    subprocess.Popen(["cmd", "/c", str(p)],
                                     creationflags=DETACHED, cwd=str(p.parent))
                else:
                    os.startfile(str(p))
                launch_btn.config(text="✓ Launched — now position your window",
                                   bg="#a6e3a1")
            except Exception as e:
                messagebox.showerror("Launch failed", str(e), parent=dlg)

        launch_btn = tk.Button(dlg, text="▶ Launch App",
                    font=("Segoe UI", 11, "bold"), fg="#ffffff", bg="#6c5ce7",
                    relief="flat", padx=20, pady=8, cursor="hand2",
                    command=_launch)
        launch_btn.pack(pady=(10, 6))

        def _capture():
            # Hide dialog briefly so it's not in the shot
            dlg.withdraw()
            self.root.withdraw()
            time.sleep(0.8)
            try:
                import win32gui
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd)
                if not hwnd or "Gallery" in title or "Capture" in title:
                    messagebox.showwarning("Wrong window",
                        "The active window looks like the Gallery itself. "
                        "Click on your target app first, then capture.",
                        parent=self.root)
                    dlg.deiconify()
                    self.root.deiconify()
                    return

                rect = win32gui.GetWindowRect(hwnd)
                x1, y1, x2, y2 = rect
                w_ = x2 - x1
                h_ = y2 - y1
                if w_ < 40 or h_ < 40:
                    messagebox.showwarning("Too small",
                        f"Window is only {w_}x{h_}. Make it bigger.",
                        parent=self.root)
                    dlg.deiconify()
                    self.root.deiconify()
                    return

                thumb_path = self._ext_thumb_path(app)
                with mss.mss() as sct:
                    region = {"left": max(0, x1 - 6), "top": max(0, y1 - 6),
                              "width": w_ + 12, "height": h_ + 12}
                    shot = sct.grab(region)
                    img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
                    img = img.resize((504, 284), Image.LANCZOS)
                    img.save(str(thumb_path), quality=92)

                # Update app with thumb path
                externals = load_external_apps()
                for e in externals:
                    if e["script"] == app["script"]:
                        e["thumb_path"] = str(thumb_path)
                        break
                save_external_apps(externals)

                self.root.deiconify()
                dlg.destroy()
                self.status_label.config(
                    text=f"✓ Captured '{title[:30]}' for {app['name']}")
                self._rebuild_gallery()
            except Exception as e:
                self.root.deiconify()
                dlg.deiconify()
                messagebox.showerror("Capture failed", str(e), parent=dlg)

        tk.Button(dlg, text="📸 Capture Active Window",
                    font=("Segoe UI", 11, "bold"), fg="#ffffff", bg="#f5c2e7",
                    relief="flat", padx=20, pady=8, cursor="hand2",
                    command=_capture).pack(pady=6)

        tk.Button(dlg, text="Cancel", font=("Segoe UI", 9),
                    fg="#888", bg="#f0f0f5", relief="flat", padx=14, pady=4,
                    cursor="hand2",
                    command=lambda: (dlg.destroy(), self._rebuild_gallery())).pack(pady=4)

    def _pick_thumbnail_file(self, app):
        """Let user pick an existing image file as the thumbnail."""
        filepath = filedialog.askopenfilename(
            parent=self.root, title="Choose thumbnail image",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp"),
                       ("All files", "*.*")])
        if not filepath:
            self._rebuild_gallery()
            return

        try:
            thumb_path = self._ext_thumb_path(app)
            img = Image.open(filepath).convert("RGB")
            img = img.resize((504, 284), Image.LANCZOS)
            img.save(str(thumb_path), quality=92)

            externals = load_external_apps()
            for e in externals:
                if e["script"] == app["script"]:
                    e["thumb_path"] = str(thumb_path)
                    break
            save_external_apps(externals)

            self.status_label.config(text=f"✓ Thumbnail set from file for {app['name']}")
        except Exception as e:
            messagebox.showerror("Image error", str(e), parent=self.root)

        self._rebuild_gallery()

    def _launch_single(self, app):
        """Launch a single app (built-in or external) without affecting others."""
        try:
            if app.get("external"):
                path_str = app.get("path", "")
                if not path_str:
                    return
                p = Path(path_str)
                if path_str.startswith(("http://", "https://")):
                    os.startfile(path_str)
                elif p.suffix.lower() == ".py":
                    subprocess.Popen([str(PYTHONW), str(p)],
                                     creationflags=DETACHED, cwd=str(p.parent))
                elif p.suffix.lower() in (".lnk", ".url"):
                    os.startfile(str(p))
                elif p.suffix.lower() in (".bat", ".cmd"):
                    subprocess.Popen(["cmd", "/c", str(p)],
                                     creationflags=DETACHED, cwd=str(p.parent))
                elif p.suffix.lower() == ".ps1":
                    subprocess.Popen(["powershell", "-File", str(p)],
                                     creationflags=DETACHED, cwd=str(p.parent))
                else:
                    os.startfile(str(p))
            else:
                path = SCRIPT_DIR / app["script"]
                if path.exists():
                    subprocess.Popen([str(PYTHONW), str(path)],
                                     creationflags=DETACHED, cwd=str(SCRIPT_DIR))
            self.status_label.config(text=f"Launched {app['name']}")
        except Exception as e:
            self.status_label.config(text=f"Launch failed: {e}")

    def _delete_external(self, app):
        """Delete an external app after confirmation."""
        if not messagebox.askyesno("Delete",
                f"Remove '{app['name']}' from your gallery?",
                parent=self.root):
            return
        externals = load_external_apps()
        externals = [e for e in externals if e["script"] != app["script"]]
        save_external_apps(externals)
        self._rebuild_gallery()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    GalleryLauncher().run()
