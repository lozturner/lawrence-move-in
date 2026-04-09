"""
Lawrence: Move In — Tiered Launcher v1.0.0
Three levels of the suite. Pick what you need right now.

Level 1 — ESSENTIALS (arms and legs)
  Hot Corners, Focus Rules, Window Tiles, App Tray, Nag
  ~80MB RAM. Lightweight. Always running. You can move around.

Level 2 — PRODUCTIVITY (brain engaged)
  + Hub, Linker, Mouse Pause, Scribe, Voice Sort, Kidlin
  ~180MB RAM. You're working. You need tools.

Level 3 — FULL SUITE (everything)
  + Watcher, NACHO, Replay, Capture, Winddown, Annoyances, Launcher
  ~320MB RAM. Full body double. Recording, AI, voice, session management.

Level 4 — GALLERY (visual picker)
  All 18 apps shown as cards with thumbnails, problem/solution, checkboxes.
  Pick exactly what you want. Run selected.

Usage:
  python launch_level.py          → interactive picker
  python launch_level.py 1        → launch level 1
  python launch_level.py 2        → launch level 2
  python launch_level.py 3        → launch level 3
  python launch_level.py 4        → gallery picker
"""
__version__ = "1.0.0"

import json, os, subprocess, sys, time, tkinter as tk
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PYTHONW    = Path(sys.executable).with_name("pythonw.exe")
DETACHED   = 0x00000008

# ── Level definitions ─────────────────────────────────────────────────────────
LEVELS = {
    1: {
        "name": "Essentials",
        "tag": "Arms & Legs",
        "color": "#a6e3a1",
        "ram_est": "~80MB",
        "desc": "The bare minimum. You can move around your OS without fighting it.",
        "scripts": [
            ("hot_corner.py",  "Hot Corners",    "Screen corner triggers — Alt+Tab, Task View, Telegram, custom files"),
            ("niggly.py",      "Focus Rules",    "IF/THEN window pairing — focus one, others get out of the way"),
            ("tiles.py",       "Window Tiles",   "Visual map of every open window as a coloured tile"),
            ("app_tray.py",    "App Tray",       "Real icons in system tray for Explorer, Edge, Chrome, Comet, Perplexity"),
            ("nag.py",         "Nag",            "Timetable nagger — reminds you what you should be doing every 5 minutes"),
        ],
    },
    2: {
        "name": "Productivity",
        "tag": "Brain Engaged",
        "color": "#89b4fa",
        "ram_est": "~180MB",
        "desc": "You're working. Voice input, phrase tools, idle detection, the hub.",
        "scripts": [
            ("hub.py",         "Hub",            "Tile launcher — see what's running, launch anything, hard reset"),
            ("linker.py",      "Linker",         "Connector phrase tiles — multi-select, zoom, AI suggest, clipboard"),
            ("mouse_pause.py", "Mouse Pause",    "Idle action panel — pops up when you stop, hands-free voice, AI input"),
            ("scribe.py",      "Scribe",         "Floating speech-to-text — offline Vosk, auto-tags content"),
            ("voicesort.py",   "Voice Sort",     "Clipboard + voice categoriser — thoughts, tasks, ideas filed to markdown"),
            ("kidlin.py",      "Kidlin's Law",   "Type messy thinking, AI returns a clean problem statement"),
        ],
    },
    3: {
        "name": "Full Suite",
        "tag": "Everything",
        "color": "#cba6f7",
        "ram_est": "~320MB",
        "desc": "Full body double. AI vision, voice assistant, recording, session management.",
        "scripts": [
            ("watcher.py",     "Watcher",        "Mouse idle → screenshot → Claude Vision tells you what you were doing"),
            ("nacho.py",       "NACHO",          "Voice AI assistant — talks to you, every sentence is a clickable action"),
            ("replay.py",      "Replay",         "Records screenshots, mouse trail, windows, clipboard. Scrub timeline."),
            ("capture.py",     "Capture",        "Screenshot + notes brain dump. Sessions, AI processing, export."),
            ("winddown.py",    "Winddown",       "Session wind-down — verifies you're done, saves state, resumes next day"),
            ("annoyances.py",  "Annoyances",     "Persistent log of computer annoyances with AI workarounds"),
            ("launcher.py",    "Master Launcher","Gamification command centre — XP, levels, glowing orbs"),
        ],
    },
}

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

def get_ram_usage():
    import psutil
    total = 0
    for p in psutil.process_iter(["name","cmdline","memory_info"]):
        try:
            cmd = p.info["cmdline"] or []
            if len(cmd)>1 and "niggly_machine" in cmd[1] and "python" in (p.info["name"] or "").lower():
                total += p.info["memory_info"].rss
        except: pass
    return total / (1024*1024)  # MB

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

def launch_scripts(scripts):
    import selfclean
    for script, name, desc in scripts:
        if selfclean.is_already_running(script):
            print(f"  SKIP    {name:<18s} (already running)")
        elif selfclean.safe_launch(script):
            print(f"  Launched {name:<18s} {desc[:60]}")
        else:
            print(f"  SKIP    {name:<18s} (file not found)")
        time.sleep(0.3)  # stagger launches to reduce CPU spike

def launch_level(level):
    """Launch a level (cumulative — level 2 includes level 1)."""
    kill_all_suite()
    time.sleep(0.5)

    all_scripts = []
    for lv in range(1, level + 1):
        lvl = LEVELS[lv]
        print(f"\n{'='*50}")
        print(f"  Level {lv}: {lvl['name']} — {lvl['tag']}")
        print(f"  {lvl['desc']}")
        print(f"{'='*50}")
        all_scripts.extend(lvl["scripts"])
        launch_scripts(lvl["scripts"])

    time.sleep(2)
    ram = get_ram_usage()
    running = get_running()
    print(f"\n{'─'*50}")
    print(f"  {len(running)} apps running | {ram:.0f}MB RAM")
    print(f"  Estimated total at steady state: {LEVELS[level]['ram_est']}")
    print(f"{'─'*50}")

# ── GUI picker ────────────────────────────────────────────────────────────────
def show_picker():
    root = tk.Tk()
    root.title("Lawrence: Move In — Choose Level")
    root.attributes("-topmost", True)
    root.configure(bg="#0a0a14")

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = 520, 480
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    tk.Label(root, text="Lawrence: Move In",
             font=("Consolas",16,"bold"), fg="#b4befe", bg="#0a0a14").pack(pady=(16,2))
    tk.Label(root, text="How much do you need right now?",
             font=("Segoe UI",10), fg="#5a5a80", bg="#0a0a14").pack(pady=(0,12))

    # Current state
    running = get_running()
    ram = get_ram_usage()
    tk.Label(root, text=f"Currently: {len(running)} apps running, {ram:.0f}MB RAM",
             font=("Segoe UI",8), fg="#5a5a80", bg="#0a0a14").pack()

    for lv in [1, 2, 3]:
        lvl = LEVELS[lv]
        col = lvl["color"]
        apps = [s[1] for s in lvl["scripts"]]

        f = tk.Frame(root, bg="#1a1a3a", padx=16, pady=12, cursor="hand2")
        f.pack(fill="x", padx=20, pady=6)

        hdr = tk.Frame(f, bg="#1a1a3a")
        hdr.pack(fill="x")

        tk.Label(hdr, text=f"Level {lv}", font=("Consolas",12,"bold"),
                 fg=col, bg="#1a1a3a").pack(side="left")
        tk.Label(hdr, text=lvl["name"], font=("Segoe UI",11,"bold"),
                 fg="#cdd6f4", bg="#1a1a3a", padx=8).pack(side="left")
        tk.Label(hdr, text=lvl["tag"], font=("Segoe UI",9),
                 fg="#5a5a80", bg="#1a1a3a").pack(side="left")
        tk.Label(hdr, text=lvl["ram_est"], font=("Consolas",9),
                 fg="#5a5a80", bg="#1a1a3a").pack(side="right")

        tk.Label(f, text=lvl["desc"], font=("Segoe UI",9),
                 fg="#a6adc8", bg="#1a1a3a", anchor="w").pack(fill="x", pady=(4,2))
        tk.Label(f, text=", ".join(apps), font=("Segoe UI",7),
                 fg="#5a5a80", bg="#1a1a3a", anchor="w", wraplength=460).pack(fill="x")

        def _enter(e, fr=f): fr.config(bg="#252545")
        def _leave(e, fr=f): fr.config(bg="#1a1a3a")
        def _click(e, level=lv):
            root.destroy()
            launch_level(level)

        for widget in [f] + list(f.winfo_children()) + [hdr] + list(hdr.winfo_children()):
            widget.bind("<Enter>", _enter)
            widget.bind("<Leave>", _leave)
            widget.bind("<Button-1>", _click)

    # Level 4 button
    f4 = tk.Frame(root, bg="#1a1a3a", padx=16, pady=12, cursor="hand2")
    f4.pack(fill="x", padx=20, pady=6)
    hdr4 = tk.Frame(f4, bg="#1a1a3a")
    hdr4.pack(fill="x")
    tk.Label(hdr4, text="Level 4", font=("Consolas",12,"bold"),
             fg="#f9e2af", bg="#1a1a3a").pack(side="left")
    tk.Label(hdr4, text="Gallery", font=("Segoe UI",11,"bold"),
             fg="#cdd6f4", bg="#1a1a3a", padx=8).pack(side="left")
    tk.Label(hdr4, text="Visual Picker", font=("Segoe UI",9),
             fg="#5a5a80", bg="#1a1a3a").pack(side="left")
    tk.Label(f4, text="Full visual gallery with thumbnails and problem/solution cards. Pick exactly what you need.",
             font=("Segoe UI",9), fg="#a6adc8", bg="#1a1a3a", anchor="w").pack(fill="x", pady=(4,2))
    def _click4(e):
        root.destroy()
        subprocess.Popen([sys.executable, str(SCRIPT_DIR / "launch_gallery.py")], cwd=str(SCRIPT_DIR))
    for w4 in [f4, hdr4] + list(f4.winfo_children()) + list(hdr4.winfo_children()):
        w4.bind("<Button-1>", _click4)

    tk.Label(root, text="Level 2 includes Level 1. Level 3 includes everything. Level 4 lets you pick.",
             font=("Segoe UI",8), fg="#5a5a80", bg="#0a0a14").pack(pady=(8,0))

    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            level = int(sys.argv[1])
            if level in (1, 2, 3):
                launch_level(level)
            elif level == 4:
                subprocess.Popen([sys.executable, str(SCRIPT_DIR / "launch_gallery.py")],
                                 cwd=str(SCRIPT_DIR))
            else:
                print("Usage: python launch_level.py [1|2|3|4]")
        except ValueError:
            print("Usage: python launch_level.py [1|2|3|4]")
    else:
        show_picker()
