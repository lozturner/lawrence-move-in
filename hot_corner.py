"""
Lawrence: Move In — Hot Corner v2.0.0
Multiple hot corners, each with independent actions.
System tray icon for settings control.
"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

# ── Win32 constants & imports ────────────────────────────────────────
user32 = ctypes.windll.user32
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_LWIN = 0x5B
VK_TAB = 0x09

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "hot_corner_config.json")

DEFAULT_CONFIG = {
    "enabled": True,
    "sensitivity_px": 5,
    "dwell_ms": 150,
    "cooldown_ms": 1000,
    "poll_ms": 30,
    "corners": {
        "top-left": {
            "enabled": True,
            "action": "task_view",
        },
        "top-right": {
            "enabled": False,
            "action": "task_view",
        },
        "bottom-left": {
            "enabled": True,
            "action": "telegram_chat",
            "telegram_chat_id": "916637857",
        },
        "bottom-right": {
            "enabled": True,
            "action": "windowbot",
        },
    },
}


# ── Config ───────────────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
        # Deep-merge corners
        cfg = {**DEFAULT_CONFIG, **saved}
        merged_corners = {}
        for corner_name in DEFAULT_CONFIG["corners"]:
            default_c = DEFAULT_CONFIG["corners"][corner_name]
            saved_c = saved.get("corners", {}).get(corner_name, {})
            merged_corners[corner_name] = {**default_c, **saved_c}
        cfg["corners"] = merged_corners
    else:
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
        save_config(cfg)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Actions — proper Win32 INPUT structs ─────────────────────────────
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]


def _send_key(vk, up=False):
    flags = KEYEVENTF_KEYUP if up else 0
    ki = KEYBDINPUT(vk, 0, flags, 0, ctypes.pointer(ctypes.c_ulong(0)))
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = ki
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def action_task_view(**_kw):
    """Win+Tab → Task View."""
    _send_key(VK_LWIN)
    _send_key(VK_TAB)
    time.sleep(0.05)
    _send_key(VK_TAB, up=True)
    _send_key(VK_LWIN, up=True)


def action_alt_tab(**_kw):
    """Alt+Tab quick switcher."""
    VK_MENU = 0x12
    _send_key(VK_MENU)
    _send_key(VK_TAB)
    time.sleep(0.05)
    _send_key(VK_TAB, up=True)
    _send_key(VK_MENU, up=True)


def action_telegram_chat(telegram_chat_id="916637857", **_kw):
    """Open Telegram to a specific chat via tg:// deep link."""
    url = f"tg://openmessage?chat_id={telegram_chat_id}"
    os.startfile(url)


def action_mouse_pause(**_kw):
    """Launch Mouse Pause panel."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mouse_pause.py")
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([pythonw, script], creationflags=0x00000008)


def action_nacho(**_kw):
    """Launch NACHO voice assistant."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nacho.py")
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([pythonw, script], creationflags=0x00000008)


def action_hub(**_kw):
    """Launch the Hub."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hub.py")
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([pythonw, script], creationflags=0x00000008)


def action_windowbot(**_kw):
    """Focus WindowBot if running, otherwise launch it. Failsafe loop."""
    import win32gui, win32con
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(script_dir, "windowbot.py")
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")

    # Try to find and focus existing WindowBot window
    for attempt in range(2):
        found = []
        def _cb(h, _):
            if win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h)
                if "windowbot" in t.lower():
                    found.append(h)
            return True
        try:
            win32gui.EnumWindows(_cb, None)
        except:
            pass

        if found:
            hwnd = found[0]
            try:
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(hwnd)
            except:
                pass
            return

        # Not found — launch it (first attempt only)
        if attempt == 0 and os.path.exists(script):
            subprocess.Popen([pythonw, script], creationflags=0x00000008,
                             cwd=script_dir)
            time.sleep(2)  # wait for it to create a window


def action_run_file(file_path="", **_kw):
    """Run any file — .exe, .py, .bat, .ps1, .rs, .c, .js, whatever."""
    if not file_path or not os.path.exists(file_path):
        return
    ext = os.path.splitext(file_path)[1].lower()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")

    if ext == ".py":
        subprocess.Popen([pythonw, file_path], creationflags=0x00000008)
    elif ext == ".pyw":
        subprocess.Popen([pythonw, file_path], creationflags=0x00000008)
    elif ext in (".exe", ".bat", ".cmd"):
        subprocess.Popen([file_path], creationflags=0x00000008, shell=True)
    elif ext == ".ps1":
        subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass",
                          "-File", file_path], creationflags=0x00000008)
    elif ext in (".rs", ".c", ".cpp"):
        # Compile-and-run: user probably wants to just open it
        os.startfile(file_path)
    else:
        # Fallback: let Windows figure it out
        os.startfile(file_path)


ACTIONS = {
    "task_view": action_task_view,
    "alt_tab": action_alt_tab,
    "telegram_chat": action_telegram_chat,
    "mouse_pause": action_mouse_pause,
    "nacho": action_nacho,
    "hub": action_hub,
    "windowbot": action_windowbot,
    "run_file": action_run_file,
}

ACTION_LABELS = {
    "task_view": "Task View (Win+Tab)",
    "alt_tab": "Alt+Tab Switcher",
    "telegram_chat": "Telegram Chat",
    "mouse_pause": "Mouse Pause Panel",
    "nacho": "NACHO Voice AI",
    "hub": "Hub Launcher",
    "windowbot": "WindowBot",
    "run_file": "Run File",
}


# ── Corner detection ─────────────────────────────────────────────────
CORNER_NAMES = ["top-left", "top-right", "bottom-left", "bottom-right"]


class HotCornerWatcher:
    def __init__(self, cfg):
        self.cfg = cfg
        self.enabled = cfg["enabled"]
        self._running = False
        self._thread = None
        self._last_trigger = {c: 0 for c in CORNER_NAMES}
        self._dwell_start = {c: 0 for c in CORNER_NAMES}

    def _which_corner(self, x, y):
        """Return which corner the cursor is in, or None."""
        s = self.cfg["sensitivity_px"]
        w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        if x <= s and y <= s:
            return "top-left"
        if x >= w - s and y <= s:
            return "top-right"
        if x <= s and y >= h - s:
            return "bottom-left"
        if x >= w - s and y >= h - s:
            return "bottom-right"
        return None

    def _poll_loop(self):
        pt = wintypes.POINT()
        while self._running:
            if not self.enabled:
                time.sleep(0.1)
                continue

            user32.GetCursorPos(ctypes.byref(pt))
            now_ms = time.time() * 1000
            hit_corner = self._which_corner(pt.x, pt.y)

            for corner_name in CORNER_NAMES:
                corner_cfg = self.cfg["corners"].get(corner_name, {})
                if not corner_cfg.get("enabled", False):
                    continue

                if hit_corner == corner_name:
                    if self._dwell_start[corner_name] == 0:
                        self._dwell_start[corner_name] = now_ms
                    elif (now_ms - self._dwell_start[corner_name] >= self.cfg["dwell_ms"]
                          and now_ms - self._last_trigger[corner_name] >= self.cfg["cooldown_ms"]):
                        self._last_trigger[corner_name] = now_ms
                        self._dwell_start[corner_name] = 0
                        action_name = corner_cfg.get("action", "task_view")
                        action_fn = ACTIONS.get(action_name, action_task_view)
                        # Pass corner config as kwargs so actions can read extra params
                        action_fn(**corner_cfg)
                else:
                    self._dwell_start[corner_name] = 0

            time.sleep(self.cfg["poll_ms"] / 1000)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False


# ── System tray ──────────────────────────────────────────────────────
def run_tray(watcher, cfg):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("Install pystray and Pillow:  pip install pystray pillow")
        print("Running without tray icon — Ctrl+C to quit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            watcher.stop()
        return

    def make_icon(enabled):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        colour = "#22c55e" if enabled else "#ef4444"
        # Four corner dots — lit if that corner is enabled
        for cx, cy, cname in [(8, 8, "top-left"), (56, 8, "top-right"),
                               (8, 56, "bottom-left"), (56, 56, "bottom-right")]:
            c_enabled = cfg["corners"].get(cname, {}).get("enabled", False)
            c_col = colour if c_enabled else "#555555"
            d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=c_col)
        # Centre square
        d.rectangle([24, 24, 40, 40], fill=colour, outline="white", width=1)
        return img

    def toggle_global(icon, item):
        watcher.enabled = not watcher.enabled
        cfg["enabled"] = watcher.enabled
        save_config(cfg)
        icon.icon = make_icon(watcher.enabled)
        icon.update_menu()

    def toggle_corner(corner_name):
        def _toggle(icon, item):
            c = cfg["corners"][corner_name]
            c["enabled"] = not c["enabled"]
            watcher.cfg["corners"][corner_name]["enabled"] = c["enabled"]
            save_config(cfg)
            icon.icon = make_icon(watcher.enabled)
            icon.update_menu()
        return _toggle

    def set_corner_action(corner_name, action_name):
        def _set(icon, item):
            cfg["corners"][corner_name]["action"] = action_name
            watcher.cfg["corners"][corner_name]["action"] = action_name
            save_config(cfg)
            icon.update_menu()
        return _set

    def browse_file_for_corner(corner_name):
        def _browse(icon, item):
            import tkinter as tk
            from tkinter import filedialog
            tmp = tk.Tk()
            tmp.withdraw()
            tmp.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                parent=tmp,
                title=f"Select file for {corner_name}",
                filetypes=[
                    ("All files", "*.*"),
                    ("Python", "*.py;*.pyw"),
                    ("Executables", "*.exe;*.bat;*.cmd"),
                    ("PowerShell", "*.ps1"),
                    ("Scripts", "*.js;*.ts;*.rs;*.c;*.cpp"),
                ])
            tmp.destroy()
            if path:
                cfg["corners"][corner_name]["action"] = "run_file"
                cfg["corners"][corner_name]["file_path"] = path
                watcher.cfg["corners"][corner_name]["action"] = "run_file"
                watcher.cfg["corners"][corner_name]["file_path"] = path
                save_config(cfg)
                icon.update_menu()
        return _browse

    def set_sensitivity(val):
        def _set(icon, item):
            cfg["sensitivity_px"] = val
            watcher.cfg["sensitivity_px"] = val
            save_config(cfg)
            icon.update_menu()
        return _set

    def set_dwell(val):
        def _set(icon, item):
            cfg["dwell_ms"] = val
            watcher.cfg["dwell_ms"] = val
            save_config(cfg)
            icon.update_menu()
        return _set

    def quit_app(icon, item):
        watcher.stop()
        icon.stop()

    CORNER_LABELS = {
        "top-left": "↖ Top-Left",
        "top-right": "↗ Top-Right",
        "bottom-left": "↙ Bottom-Left",
        "bottom-right": "↘ Bottom-Right",
    }

    def build_menu():
        corner_items = []
        for cname in CORNER_NAMES:
            c_cfg = cfg["corners"][cname]
            c_on = c_cfg.get("enabled", False)
            c_action = c_cfg.get("action", "task_view")
            label = CORNER_LABELS[cname]
            if c_action == "run_file" and c_on:
                fp = c_cfg.get("file_path", "")
                status = f"Run: {os.path.basename(fp)}" if fp else "Run File (none set)"
            else:
                status = ACTION_LABELS.get(c_action, c_action) if c_on else "Off"

            # Build file info if this corner runs a file
            file_path = c_cfg.get("file_path", "")
            file_short = os.path.basename(file_path) if file_path else ""

            action_items = [
                pystray.MenuItem(
                    f"{'✓ Enabled' if c_on else '✗ Disabled'}",
                    toggle_corner(cname),
                ),
                pystray.Menu.SEPARATOR,
            ]
            for aname, alabel in ACTION_LABELS.items():
                if aname == "run_file":
                    continue  # shown separately below
                action_items.append(pystray.MenuItem(
                    alabel, set_corner_action(cname, aname),
                    checked=lambda _, _cn=cname, _an=aname: cfg["corners"][_cn]["action"] == _an,
                ))
            action_items.append(pystray.Menu.SEPARATOR)
            action_items.append(pystray.MenuItem(
                f"📂 Browse file…{('  [' + file_short + ']') if file_short else ''}",
                browse_file_for_corner(cname),
            ))

            action_submenu = pystray.Menu(*action_items)
            corner_items.append(
                pystray.MenuItem(f"{label}  [{status}]", action_submenu)
            )

        return pystray.Menu(
            pystray.MenuItem(
                lambda _: f"{'✓ All Enabled' if watcher.enabled else '✗ All Disabled'}",
                toggle_global,
            ),
            pystray.Menu.SEPARATOR,
            *corner_items,
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sensitivity", pystray.Menu(
                pystray.MenuItem("3 px (tight)",   set_sensitivity(3),
                                 checked=lambda _: cfg["sensitivity_px"] == 3),
                pystray.MenuItem("5 px (default)", set_sensitivity(5),
                                 checked=lambda _: cfg["sensitivity_px"] == 5),
                pystray.MenuItem("10 px (easy)",   set_sensitivity(10),
                                 checked=lambda _: cfg["sensitivity_px"] == 10),
                pystray.MenuItem("20 px (large)",  set_sensitivity(20),
                                 checked=lambda _: cfg["sensitivity_px"] == 20),
            )),
            pystray.MenuItem("Dwell Time", pystray.Menu(
                pystray.MenuItem("50 ms (instant)",  set_dwell(50),
                                 checked=lambda _: cfg["dwell_ms"] == 50),
                pystray.MenuItem("150 ms (default)", set_dwell(150),
                                 checked=lambda _: cfg["dwell_ms"] == 150),
                pystray.MenuItem("300 ms (slow)",    set_dwell(300),
                                 checked=lambda _: cfg["dwell_ms"] == 300),
                pystray.MenuItem("500 ms (careful)", set_dwell(500),
                                 checked=lambda _: cfg["dwell_ms"] == 500),
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Hot Corner", quit_app),
        )

    icon = pystray.Icon(
        "hot_corner",
        make_icon(watcher.enabled),
        "Hot Corner",
        menu=build_menu(),
    )
    icon.run()


# ── Main ─────────────────────────────────────────────────────────────
def main():
    cfg = load_config()
    watcher = HotCornerWatcher(cfg)
    watcher.start()
    run_tray(watcher, cfg)


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("hot_corner.py")
    main()
