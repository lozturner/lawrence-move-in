"""
Lawrence: Move In — FloatBar v1.0.0
Always-on-top 400×100 floating toolbar.
4 buttons: back to last window, next window, + 2 TBD.
System tray. Drag anywhere. Low-level win32 for instant response.
Starts with Windows.
"""
__version__ = "1.0.0"
import selfclean; selfclean.ensure_single("floatbar.py")

import ctypes, json, os, sys, threading, time, winreg
import tkinter as tk
from pathlib import Path
from PIL import Image as PILImage, ImageDraw

import win32gui, win32con, win32api, win32process
import psutil, pystray

SCRIPT_DIR = Path(__file__).resolve().parent

# ── Colours ────────────────────────────────────────────────────────────────────
BG     = "#0d1117"
BG2    = "#161b22"
BG3    = "#21262d"
FG     = "#e6edf3"
FG_DIM = "#6e7681"
BLUE   = "#79c0ff"
GREEN  = "#7ee787"
YELLOW = "#e3b341"
PURPLE = "#d2a8ff"
RED    = "#ff7b72"
TEAL   = "#76e3ea"

BTN_BG_BACK = "#1a2535"
BTN_BG_NEXT = "#1a3525"
BTN_BG_TBD  = "#21262d"

# ── Window history tracker ─────────────────────────────────────────────────────
class WindowHistory:
    """Tracks the last N foreground windows so we can go back."""
    def __init__(self, maxlen: int = 40):
        self._stack: list[int] = []   # HWNDs, newest at end
        self._maxlen = maxlen
        self._watching = False
        self._lock = threading.Lock()

    def start(self):
        self._watching = True
        threading.Thread(target=self._poll, daemon=True).start()

    def stop(self):
        self._watching = False

    def _poll(self):
        last = 0
        while self._watching:
            time.sleep(0.15)
            try:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd and hwnd != last:
                    # Skip our own floatbar windows
                    try:
                        t = win32gui.GetWindowText(hwnd)
                        if "FloatBar" in t or not t:
                            last = hwnd; continue
                    except: pass
                    with self._lock:
                        # Remove if already present (move to top)
                        if hwnd in self._stack:
                            self._stack.remove(hwnd)
                        self._stack.append(hwnd)
                        if len(self._stack) > self._maxlen:
                            self._stack.pop(0)
                    last = hwnd
            except: pass

    def go_back(self) -> bool:
        """Focus the window before the current one."""
        with self._lock:
            stack = list(self._stack)
        # Current foreground is last item; go to second-to-last
        try:
            current = win32gui.GetForegroundWindow()
        except:
            current = 0
        # Walk backwards skipping current and dead HWNDs
        for hwnd in reversed(stack[:-1]):
            if hwnd == current:
                continue
            if not self._focus(hwnd):
                continue
            return True
        return False

    def go_forward(self) -> bool:
        """Focus the next window in history (forward direction)."""
        with self._lock:
            stack = list(self._stack)
        try:
            current = win32gui.GetForegroundWindow()
        except:
            current = 0
        # Find current in stack and go one step forward
        try:
            idx = stack.index(current)
        except ValueError:
            idx = len(stack) - 1
        for hwnd in stack[idx+1:]:
            if not self._focus(hwnd):
                continue
            return True
        return False

    @staticmethod
    def _focus(hwnd: int) -> bool:
        """Try to bring hwnd to the foreground. Returns True on success."""
        try:
            if not win32gui.IsWindow(hwnd):
                return False
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            # Thread-attach trick for cross-process focus
            cur_tid = win32api.GetCurrentThreadId()
            tgt_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
            if cur_tid != tgt_tid:
                ctypes.windll.user32.AttachThreadInput(cur_tid, tgt_tid, True)
            win32gui.SetForegroundWindow(hwnd)
            if cur_tid != tgt_tid:
                ctypes.windll.user32.AttachThreadInput(cur_tid, tgt_tid, False)
            return True
        except:
            return False


# ── Startup registry helpers ───────────────────────────────────────────────────
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LawrenceFloatBar"

def _startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except: return False

def _enable_startup():
    pw  = str(Path(sys.executable).with_name("pythonw.exe"))
    cmd = f'"{pw}" "{SCRIPT_DIR / "floatbar.py"}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)

def _disable_startup():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
    except: pass

# Auto-enable at first run
if not _startup_enabled():
    try: _enable_startup()
    except: pass


# ── FloatBar ───────────────────────────────────────────────────────────────────
class FloatBar:
    W, H = 400, 88

    def __init__(self):
        self._hist  = WindowHistory()
        self._hist.start()
        self._dragging = False
        self._drag_ox = self._drag_oy = 0

        self.root = tk.Tk()
        self.root.overrideredirect(True)          # no title bar
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg=BG)
        self.root.geometry(f"{self.W}x{self.H}+60+60")
        self.root.resizable(False, False)

        # Keep always-on-top via periodic lift
        self.root.after(500, self._keep_top)

        self._build_ui()
        self._build_tray()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BG, highlightthickness=1,
                         highlightbackground=BG3)
        outer.pack(fill="both", expand=True)

        # Drag handle strip at the top
        drag = tk.Frame(outer, bg=BG2, height=14, cursor="fleur")
        drag.pack(fill="x", side="top")
        tk.Label(drag, text=f"FloatBar  v{__version__}",
                 font=("Segoe UI", 6), fg=FG_DIM, bg=BG2).pack(side="left", padx=6)
        tk.Label(drag, text="· drag to move · right-click = menu",
                 font=("Segoe UI", 6), fg=FG_DIM, bg=BG2).pack(side="left")

        drag.bind("<ButtonPress-1>",   self._drag_start)
        drag.bind("<B1-Motion>",       self._drag_move)
        drag.bind("<ButtonRelease-1>", self._drag_end)
        drag.bind("<Button-3>",        self._show_menu)

        # Buttons row
        btn_row = tk.Frame(outer, bg=BG, pady=6, padx=6)
        btn_row.pack(fill="both", expand=True)

        self._btns = []

        def _btn(parent, text, color, bg, cmd, col):
            f = tk.Frame(parent, bg=bg, highlightthickness=1,
                         highlightbackground=color + "55")
            f.grid(row=0, column=col, sticky="nsew", padx=3, pady=2)
            lbl = tk.Label(f, text=text, font=("Segoe UI", 8, "bold"),
                           fg=color, bg=bg, wraplength=82,
                           justify="center", cursor="hand2")
            lbl.pack(expand=True, fill="both", pady=6, padx=4)
            for w in (f, lbl):
                w.bind("<Button-1>", lambda e, c=cmd: c())
                w.bind("<Enter>",    lambda e, fr=f, c=color: fr.config(
                    highlightbackground=c))
                w.bind("<Leave>",    lambda e, fr=f, c=color: fr.config(
                    highlightbackground=c+"55"))
            self._btns.append((f, lbl))
            return f, lbl

        btn_row.columnconfigure(0, weight=1, uniform="btn")
        btn_row.columnconfigure(1, weight=1, uniform="btn")
        btn_row.columnconfigure(2, weight=1, uniform="btn")
        btn_row.columnconfigure(3, weight=1, uniform="btn")
        btn_row.rowconfigure(0, weight=1)

        _btn(btn_row, "← Back to\nlast thing", BLUE,  BTN_BG_BACK, self._do_back,    0)
        _btn(btn_row, "→ On to\nnext thing",   GREEN, BTN_BG_NEXT, self._do_next,    1)
        self._tbd1_f, self._tbd1_l = _btn(btn_row, "[ · · · ]",   FG_DIM, BTN_BG_TBD, lambda: None, 2)
        self._tbd2_f, self._tbd2_l = _btn(btn_row, "[ · · · ]",   FG_DIM, BTN_BG_TBD, lambda: None, 3)

        # Status bar
        self._status = tk.Label(outer, text="Ready",
                                font=("Segoe UI", 6), fg=FG_DIM, bg=BG2, pady=1)
        self._status.pack(fill="x", side="bottom")
        outer.bind("<Button-3>", self._show_menu)

    # ── Actions ────────────────────────────────────────────────────────────────

    def _flash(self, idx: int, success: bool):
        """Briefly flash a button green (success) or red (fail)."""
        try:
            f, lbl = self._btns[idx]
            orig_bg = f["bg"]
            f.config(  bg=GREEN+"22" if success else RED+"22")
            lbl.config(bg=GREEN+"22" if success else RED+"22")
            self.root.after(300, lambda: (f.config(bg=orig_bg),
                                          lbl.config(bg=orig_bg)))
        except: pass

    def _do_back(self):
        self._status.config(text="← Going back…", fg=BLUE)
        ok = self._hist.go_back()
        self._flash(0, ok)
        self.root.after(600, lambda: self._status.config(text="Ready", fg=FG_DIM))

    def _do_next(self):
        self._status.config(text="→ Going forward…", fg=GREEN)
        ok = self._hist.go_forward()
        self._flash(1, ok)
        self.root.after(600, lambda: self._status.config(text="Ready", fg=FG_DIM))

    # ── Drag ───────────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._dragging = True
        self._drag_ox  = e.x_root - self.root.winfo_x()
        self._drag_oy  = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        if self._dragging:
            x = e.x_root - self._drag_ox
            y = e.y_root - self._drag_oy
            self.root.geometry(f"+{x}+{y}")

    def _drag_end(self, e):
        self._dragging = False

    # ── Keep on top ────────────────────────────────────────────────────────────

    def _keep_top(self):
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
        except: pass
        self.root.after(800, self._keep_top)

    # ── Context menu ───────────────────────────────────────────────────────────

    def _show_menu(self, e=None):
        m = tk.Menu(self.root, tearoff=0, bg=BG2, fg=FG,
                    activebackground=BG3, activeforeground=FG,
                    font=("Segoe UI", 9), bd=0)
        startup_lbl = ("✓ Start with Windows" if _startup_enabled()
                       else "   Start with Windows")
        m.add_command(label=startup_lbl, command=self._toggle_startup)
        m.add_separator()
        m.add_command(label="   Quit FloatBar", foreground=RED,
                      command=self._quit)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _toggle_startup(self):
        if _startup_enabled(): _disable_startup()
        else: _enable_startup()

    # ── Tray ───────────────────────────────────────────────────────────────────

    def _build_tray(self):
        img = PILImage.new("RGBA", (64, 64), (0,0,0,0))
        d   = ImageDraw.Draw(img)
        # Left arrow (blue)
        d.polygon([(4,32),(22,18),(22,46)], fill="#79c0ff")
        # Right arrow (green)
        d.polygon([(60,32),(42,18),(42,46)], fill="#7ee787")
        # Centre bar (white)
        d.rectangle([22,28,42,36], fill="#ffffff")

        menu = pystray.Menu(
            pystray.MenuItem(f"FloatBar v{__version__}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show",  lambda: self.root.after(0, self._show_window)),
            pystray.MenuItem("Hide",  lambda: self.root.after(0, self._hide_window)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start with Windows",
                             lambda: (_enable_startup() if not _startup_enabled()
                                      else _disable_startup())),
            pystray.MenuItem("Quit",  self._quit),
        )
        self._tray = pystray.Icon("floatbar", img, f"FloatBar v{__version__}", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _show_window(self):
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.lift()

    def _hide_window(self):
        self.root.withdraw()

    def _quit(self, *_):
        self._hist.stop()
        try: self._tray.stop()
        except: pass
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    FloatBar().run()
