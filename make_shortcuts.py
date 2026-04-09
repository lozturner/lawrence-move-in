"""
Lawrence: Move In — Desktop Shortcut Maker
Run once: drops .lnk files on your Desktop.
Double-click any of them — no chat, no terminal, no Python visible.
"""
import os
import sys
from pathlib import Path

import win32com.client

SUITE_DIR  = Path(__file__).resolve().parent
DESKTOP    = Path(os.environ["USERPROFILE"]) / "Desktop"
PYTHONW    = Path(sys.executable).with_name("pythonw.exe")
MOVEIN_EXE = SUITE_DIR / "movein.exe"   # use as icon source

# (lnk_name, script, description, icon_idx)
# icon_idx: movein.exe embeds one icon at index 0
SHORTCUTS = [
    ("Lawrence — Hub",          "hub.py",          "Floating tile launcher for the full suite"),
    ("Lawrence — Launch All",   "launch_all.pyw",  "Start every applet in one click"),
    ("Lawrence — Focus Rules",  "niggly.py",       "IF/THEN window focus rules"),
    ("Lawrence — Window Tiles", "tiles.py",        "Window tile sidebar + canvas"),
    ("Lawrence — Master Launcher","launcher.py",   "Gamification command centre"),
    ("Lawrence — Watcher",      "watcher.py",      "Mouse-idle screenshot + Claude Vision"),
    ("Lawrence — Voice Sort",   "voicesort.py",    "Clipboard/voice AI categoriser"),
    ("Lawrence — Kidlin",       "kidlin.py",       "Clarify the actual problem"),
    ("Lawrence — Scribe",       "scribe.py",       "Floating speech-to-text"),
    ("Lawrence — Annoyances",   "annoyances.py",   "Persistent computer annoyance log"),
    ("Lawrence — Hot Corners",  "hot_corner.py",   "Hot corner triggers"),
    ("Lawrence — Linker",       "linker.py",       "Connector phrase tiles"),
    ("Lawrence — Mouse Pause",  "mouse_pause.py",  "Idle action panel"),
    ("Lawrence — NACHO",        "nacho.py",        "Loz AI voice assistant"),
    ("Lawrence — Kill All",     "kill_all.py",     "Kill every applet"),
    ("Lawrence — Replay",       "replay.py",       "Record and replay desktop sessions"),
    ("Lawrence — Capture",      "capture.py",      "Screenshot + notes brain dump"),
    ("Lawrence — Winddown",     "winddown.py",     "Session wind-down + resume"),
    ("Lawrence — Nag",          "nag.py",          "Timetable nagger"),
    ("Lawrence — Level 4 Gallery", "launch_gallery.py", "Visual gallery — pick apps with thumbnails"),
    ("Lawrence — Steps",        "steps.py",        "Steps recorder — clicks, keys, windows, screenshots"),
    ("Lawrence — AI Timer",     "aitimer.py",      "Track time in LLM chats with check-ins"),
]

shell = win32com.client.Dispatch("WScript.Shell")

created = []
for lnk_name, script, desc in SHORTCUTS:
    script_path = SUITE_DIR / script
    if not script_path.exists():
        print(f"  SKIP  {script}  (not found)")
        continue

    lnk_path = str(DESKTOP / f"{lnk_name}.lnk")
    sc = shell.CreateShortCut(lnk_path)
    sc.TargetPath       = str(PYTHONW)
    sc.Arguments        = f'"{script_path}"'
    sc.WorkingDirectory = str(SUITE_DIR)
    sc.Description      = f"Lawrence: Move In — {desc}"
    sc.WindowStyle      = 7

    if MOVEIN_EXE.exists():
        sc.IconLocation = f"{MOVEIN_EXE},0"
    else:
        sc.IconLocation = f"{PYTHONW},0"

    sc.save()
    created.append(lnk_name)
    print(f"  OK    {lnk_name}.lnk")

print(f"\n{len(created)} shortcuts dropped on Desktop.")
print("Done — close this window.")
