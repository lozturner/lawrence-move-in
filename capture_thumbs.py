"""
Capture real screenshots of every applet for the Level 4 Gallery.
Launches each app, waits for its window, screenshots the window, kills it, moves on.
"""
import ctypes, json, os, subprocess, sys, time, traceback
from pathlib import Path
from ctypes import wintypes

import win32gui, win32con, win32process, win32api
import psutil
from PIL import Image
import mss

SCRIPT_DIR = Path(__file__).resolve().parent
THUMB_DIR  = SCRIPT_DIR / "thumbnails"
THUMB_DIR.mkdir(exist_ok=True)
PYTHON     = sys.executable
PYTHONW    = Path(PYTHON).with_name("pythonw.exe")
DETACHED   = 0x00000008

# Apps to capture — in order, with window title substrings to find them
APPS = [
    ("hot_corner.py",   "Hot Corners",    ["Hot Corner"]),
    ("niggly.py",       "Focus Rules",    ["Niggly Machine", "Focus Rules"]),
    ("tiles.py",        "Window Tiles",   ["Window Tiles"]),
    ("app_tray.py",     "App Tray",       []),  # tray only, screenshot desktop
    ("nag.py",          "Nag",            ["Nag", "Hey."]),
    ("hub.py",          "Hub",            ["Hub", "Lawrence"]),
    ("linker.py",       "Linker",         ["Linker", "Phrase"]),
    ("mouse_pause.py",  "Mouse Pause",    []),  # needs idle, screenshot desktop
    ("scribe.py",       "Scribe",         ["Scribe", "Live Scribe"]),
    ("voicesort.py",    "Voice Sort",     ["Voice Sort", "Clipboard"]),
    ("kidlin.py",       "Kidlin",         ["Kidlin"]),
    ("watcher.py",      "Watcher",        ["Watcher", "Lawrence"]),
    ("nacho.py",        "NACHO",          ["NACHO", "Nacho"]),
    ("replay.py",       "Replay",         ["Replay"]),
    ("capture.py",      "Capture",        ["Capture"]),
    ("winddown.py",     "Winddown",       ["Winddown", "Wind Down"]),
    ("annoyances.py",   "Annoyances",     ["Annoyances", "Annoy"]),
    ("launcher.py",     "Master Launcher",["Lawrence: Move In", "Move In"]),
]


def find_window_by_titles(title_subs, timeout=6):
    """Find a window matching any of the title substrings. Returns hwnd or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = []
        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                for sub in title_subs:
                    if sub.lower() in title.lower():
                        found.append(hwnd)
                        return False  # stop enum
            return True
        try:
            win32gui.EnumWindows(callback, None)
        except:
            pass
        if found:
            return found[0]
        time.sleep(0.5)
    return None


def find_window_by_pid(pid, timeout=6):
    """Find the main window for a given PID."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = []
        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                    if wpid == pid:
                        title = win32gui.GetWindowText(hwnd)
                        if title and len(title) > 1:
                            found.append(hwnd)
                except:
                    pass
            return True
        try:
            win32gui.EnumWindows(callback, None)
        except:
            pass
        if found:
            return found[0]
        time.sleep(0.5)
    return None


def screenshot_window(hwnd, out_path, pad=8):
    """Screenshot a specific window region from the desktop."""
    try:
        # Bring to front
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.3)
    except:
        pass

    try:
        rect = win32gui.GetWindowRect(hwnd)
        x1, y1, x2, y2 = rect
        # Add padding
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = x2 + pad
        y2 = y2 + pad
        w = x2 - x1
        h = y2 - y1
        if w < 50 or h < 50:
            return False

        with mss.mss() as sct:
            region = {"left": x1, "top": y1, "width": w, "height": h}
            shot = sct.grab(region)
            img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
            # Resize to thumbnail
            img = img.resize((504, 284), Image.LANCZOS)
            img.save(str(out_path), quality=92)
            return True
    except Exception as e:
        print(f"    Screenshot error: {e}")
        return False


def screenshot_desktop(out_path):
    """Full desktop screenshot as fallback."""
    with mss.mss() as sct:
        mon = sct.monitors[1]  # primary monitor
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
        img = img.resize((504, 284), Image.LANCZOS)
        img.save(str(out_path), quality=92)
        return True


def kill_script(script_name):
    """Kill all instances of a script."""
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
            if len(cmd) > 1 and script_name in cmd[1] and "python" in (p.info["name"] or "").lower():
                p.kill()
        except:
            pass


def capture_one(script, name, title_subs):
    """Launch, screenshot, kill one app. Returns True on success."""
    out_path = THUMB_DIR / f"{script.replace('.py', '')}.png"
    script_path = SCRIPT_DIR / script

    if not script_path.exists():
        print(f"  SKIP {name} — {script} not found")
        return False

    print(f"  Launching {name}...")

    # Use python.exe (not pythonw) so we can track PID reliably
    proc = subprocess.Popen(
        [str(PYTHONW), str(script_path)],
        creationflags=DETACHED,
        cwd=str(SCRIPT_DIR)
    )
    pid = proc.pid

    # Wait for window
    hwnd = None
    if title_subs:
        hwnd = find_window_by_titles(title_subs, timeout=8)

    if not hwnd:
        hwnd = find_window_by_pid(pid, timeout=5)

    if hwnd:
        title = win32gui.GetWindowText(hwnd)
        print(f"    Found window: '{title}' (hwnd={hwnd})")
        ok = screenshot_window(hwnd, out_path)
        if ok:
            print(f"    Saved: {out_path.name}")
        else:
            print(f"    Window screenshot failed, using desktop")
            screenshot_desktop(out_path)
    else:
        # Tray-only app or slow starter — screenshot desktop
        print(f"    No window found, using desktop screenshot")
        time.sleep(2)
        screenshot_desktop(out_path)

    # Kill it
    time.sleep(0.5)
    kill_script(script)
    try:
        proc.kill()
    except:
        pass
    time.sleep(0.5)

    print(f"    Done: {name}")
    return True


def main():
    print("=" * 60)
    print("  Lawrence: Move In — Thumbnail Capture")
    print(f"  Capturing {len(APPS)} apps...")
    print("=" * 60)

    # Kill everything first
    for script, _, _ in APPS:
        kill_script(script)
    time.sleep(1)

    success = 0
    for i, (script, name, titles) in enumerate(APPS):
        print(f"\n[{i+1}/{len(APPS)}] {name}")
        try:
            if capture_one(script, name, titles):
                success += 1
        except Exception as e:
            print(f"    ERROR: {e}")
            traceback.print_exc()

        # Clean up between captures
        kill_script(script)
        time.sleep(0.5)

    # Final cleanup
    for script, _, _ in APPS:
        kill_script(script)

    print(f"\n{'=' * 60}")
    print(f"  Done! {success}/{len(APPS)} thumbnails captured")
    print(f"  Saved to: {THUMB_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
