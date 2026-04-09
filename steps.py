"""
Lawrence: Move In — Steps Recorder v1.0.0
Records every user action (click, keystroke, window switch) with screenshots,
window handles, process data, and clipboard state. Presents a navigable
step-by-step report at session end.

Usage:
  python steps.py
  Double-click "Lawrence — Steps" desktop shortcut

Tray icon: red ● when recording, grey ○ when idle.
"""
__version__ = "1.0.0"
import selfclean; selfclean.ensure_single("steps.py")

import ctypes, json, os, subprocess, sys, time, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from collections import OrderedDict
import win32gui, win32process, win32api, win32con
import psutil
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageGrab
import mss

SCRIPT_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = SCRIPT_DIR / "steps_sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# ── Low-level hooks via ctypes ────────────────────────────────────────────────
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
HC_ACTION = 0

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p)

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("flags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", ctypes.c_ulong), ("scanCode", ctypes.c_ulong),
                ("flags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

# VK code to readable name
VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x10: "Shift",
    0x11: "Ctrl", 0x12: "Alt", 0x14: "CapsLock", 0x1B: "Escape",
    0x20: "Space", 0x21: "PageUp", 0x22: "PageDown", 0x23: "End",
    0x24: "Home", 0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2C: "PrintScreen", 0x2D: "Insert", 0x2E: "Delete",
    0x5B: "Win", 0x5C: "Win", 0x5D: "Menu",
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5",
    0x75: "F6", 0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10",
    0x7A: "F11", 0x7B: "F12",
    0xA0: "LShift", 0xA1: "RShift", 0xA2: "LCtrl", 0xA3: "RCtrl",
    0xA4: "LAlt", 0xA5: "RAlt",
}

def vk_to_name(vk):
    if vk in VK_NAMES:
        return VK_NAMES[vk]
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    return f"VK_{vk:#04x}"


# ── Window info snapshot ──────────────────────────────────────────────────────
def get_window_info(hwnd=None):
    """Get info about the foreground window or a specific hwnd."""
    if hwnd is None:
        hwnd = win32gui.GetForegroundWindow()
    info = {"hwnd": hwnd, "title": "", "exe": "", "pid": 0,
            "class": "", "rect": (0, 0, 0, 0)}
    try:
        info["title"] = win32gui.GetWindowText(hwnd)
        info["class"] = win32gui.GetClassName(hwnd)
        info["rect"] = win32gui.GetWindowRect(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        info["pid"] = pid
        try:
            p = psutil.Process(pid)
            info["exe"] = p.name()
        except:
            pass
    except:
        pass
    return info


def get_clipboard_text():
    """Get current clipboard text safely."""
    try:
        win32api.OpenClipboard(0)
        try:
            if win32api.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                data = win32api.GetClipboardData(win32con.CF_UNICODETEXT)
                return str(data)[:500] if data else ""
        finally:
            win32api.CloseClipboard()
    except:
        pass
    return ""


def get_all_windows():
    """Enumerate all visible windows."""
    windows = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if t and len(t) > 1:
                info = get_window_info(hwnd)
                windows.append(info)
        return True
    try:
        win32gui.EnumWindows(cb, None)
    except:
        pass
    return windows


# ── Screenshot helper ─────────────────────────────────────────────────────────
def take_screenshot(save_path, region=None):
    """Take a screenshot of the full screen or a region. Returns PIL Image."""
    try:
        with mss.mss() as sct:
            if region:
                shot = sct.grab(region)
            else:
                shot = sct.grab(sct.monitors[1])  # primary monitor
            img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
            img.save(str(save_path), quality=85)
            return img
    except Exception as e:
        return None


# ── Step data structure ───────────────────────────────────────────────────────
class Step:
    __slots__ = ("index", "timestamp", "action", "detail",
                 "window", "all_windows", "clipboard",
                 "mouse_pos", "screenshot_path", "annotations")

    def __init__(self, index, action, detail="", mouse_pos=(0,0)):
        self.index = index
        self.timestamp = datetime.now().isoformat()
        self.action = action          # "click", "right_click", "keystroke", "window_switch", "typing"
        self.detail = detail          # "Left click at (450, 320)" or "Typed: hello world"
        self.window = get_window_info()
        self.all_windows = []         # filled on clicks only (expensive)
        self.clipboard = ""
        self.mouse_pos = mouse_pos
        self.screenshot_path = ""
        self.annotations = []         # red circle, arrow, highlight

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "action": self.action,
            "detail": self.detail,
            "window": {
                "hwnd": self.window["hwnd"],
                "title": self.window["title"],
                "exe": self.window["exe"],
                "pid": self.window["pid"],
                "class": self.window["class"],
                "rect": list(self.window["rect"]),
            },
            "mouse_pos": list(self.mouse_pos),
            "clipboard": self.clipboard,
            "screenshot": self.screenshot_path,
        }


# ── Recorder engine ──────────────────────────────────────────────────────────
class StepsRecorder:
    def __init__(self):
        self.recording = False
        self.steps = []
        self.session_dir = None
        self.session_id = ""
        self._step_counter = 0
        self._mouse_hook = None
        self._kb_hook = None
        self._hook_thread = None
        self._typing_buffer = []
        self._typing_timer = None
        self._last_window_hwnd = 0
        self._lock = threading.Lock()
        # Keep references to prevent GC of hook procs
        self._mouse_proc = HOOKPROC(self._mouse_callback)
        self._kb_proc = HOOKPROC(self._kb_callback)

    def start_session(self):
        """Begin a new recording session."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = ts
        self.session_dir = SESSIONS_DIR / ts
        self.session_dir.mkdir(exist_ok=True)
        (self.session_dir / "screenshots").mkdir(exist_ok=True)
        self.steps = []
        self._step_counter = 0
        self._typing_buffer = []
        self._last_window_hwnd = win32gui.GetForegroundWindow()
        self.recording = True
        self._install_hooks()

    def stop_session(self):
        """End the current recording session."""
        self.recording = False
        self._flush_typing()
        self._remove_hooks()
        self._save_session()

    def _install_hooks(self):
        """Install mouse and keyboard hooks on a dedicated thread."""
        def _hook_loop():
            self._mouse_hook = user32.SetWindowsHookExW(
                WH_MOUSE_LL, self._mouse_proc,
                kernel32.GetModuleHandleW(None), 0)
            self._kb_hook = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._kb_proc,
                kernel32.GetModuleHandleW(None), 0)

            msg = ctypes.wintypes.MSG()
            while self.recording:
                if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.01)

        self._hook_thread = threading.Thread(target=_hook_loop, daemon=True)
        self._hook_thread.start()

    def _remove_hooks(self):
        """Remove installed hooks."""
        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
        if self._kb_hook:
            user32.UnhookWindowsHookEx(self._kb_hook)
            self._kb_hook = None

    def _mouse_callback(self, nCode, wParam, lParam):
        """Low-level mouse hook callback."""
        if nCode == HC_ACTION and self.recording:
            ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            pos = (ms.x, ms.y)

            action = None
            detail = ""
            if wParam == WM_LBUTTONDOWN:
                action = "click"
                detail = f"Left click at ({ms.x}, {ms.y})"
            elif wParam == WM_RBUTTONDOWN:
                action = "right_click"
                detail = f"Right click at ({ms.x}, {ms.y})"
            elif wParam == WM_MBUTTONDOWN:
                action = "middle_click"
                detail = f"Middle click at ({ms.x}, {ms.y})"

            if action:
                self._flush_typing()
                threading.Thread(target=self._record_click,
                                 args=(action, detail, pos), daemon=True).start()

        return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

    def _kb_callback(self, nCode, wParam, lParam):
        """Low-level keyboard hook callback."""
        if nCode == HC_ACTION and self.recording:
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = kb.vkCode
                key_name = vk_to_name(vk)

                # Modifier keys — don't record individually
                if vk in (0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
                    pass
                # Printable chars — buffer for "typing" grouping
                elif len(key_name) == 1 or key_name == "Space":
                    char = " " if key_name == "Space" else key_name.lower()
                    # Check shift
                    if win32api.GetAsyncKeyState(0x10) & 0x8000:
                        char = char.upper()
                    self._typing_buffer.append(char)
                    # Reset flush timer
                    if self._typing_timer:
                        self._typing_timer.cancel()
                    self._typing_timer = threading.Timer(1.5, self._flush_typing)
                    self._typing_timer.daemon = True
                    self._typing_timer.start()
                else:
                    # Special key — flush typing first, then record the key
                    self._flush_typing()
                    threading.Thread(target=self._record_keystroke,
                                     args=(key_name,), daemon=True).start()

        return user32.CallNextHookEx(self._kb_hook, nCode, wParam, lParam)

    def _record_click(self, action, detail, pos):
        """Record a mouse click step with screenshot and context."""
        with self._lock:
            self._step_counter += 1
            idx = self._step_counter

        step = Step(idx, action, detail, pos)
        step.clipboard = get_clipboard_text()
        step.all_windows = get_all_windows()

        # Check for window switch
        current_hwnd = win32gui.GetForegroundWindow()
        if current_hwnd != self._last_window_hwnd:
            self._last_window_hwnd = current_hwnd

        # Screenshot with click indicator
        ss_name = f"step_{idx:04d}.jpg"
        ss_path = self.session_dir / "screenshots" / ss_name
        img = take_screenshot(ss_path)
        if img:
            # Draw red circle at click position
            draw = ImageDraw.Draw(img)
            cx, cy = pos
            r = 18
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline="red", width=3)
            draw.ellipse([cx-4, cy-4, cx+4, cy+4], fill="red")
            img.save(str(ss_path), quality=85)
            step.screenshot_path = str(ss_path)

        with self._lock:
            self.steps.append(step)

    def _record_keystroke(self, key_name):
        """Record a special keystroke step."""
        with self._lock:
            self._step_counter += 1
            idx = self._step_counter

        step = Step(idx, "keystroke", f"Key: {key_name}")
        step.clipboard = get_clipboard_text()

        # Screenshot for special keys (Enter, Escape, F-keys, etc.)
        ss_name = f"step_{idx:04d}.jpg"
        ss_path = self.session_dir / "screenshots" / ss_name
        take_screenshot(ss_path)
        step.screenshot_path = str(ss_path)

        with self._lock:
            self.steps.append(step)

    def _flush_typing(self):
        """Flush the typing buffer into a single 'typing' step."""
        if not self._typing_buffer:
            return
        text = "".join(self._typing_buffer)
        self._typing_buffer = []

        if self._typing_timer:
            self._typing_timer.cancel()
            self._typing_timer = None

        with self._lock:
            self._step_counter += 1
            idx = self._step_counter

        step = Step(idx, "typing", f"Typed: {text}")
        step.clipboard = get_clipboard_text()

        # Screenshot
        ss_name = f"step_{idx:04d}.jpg"
        ss_path = self.session_dir / "screenshots" / ss_name
        take_screenshot(ss_path)
        step.screenshot_path = str(ss_path)

        with self._lock:
            self.steps.append(step)

    def _save_session(self):
        """Save the complete session to JSON and generate the report."""
        if not self.session_dir:
            return

        # JSON export
        data = {
            "session_id": self.session_id,
            "total_steps": len(self.steps),
            "start_time": self.steps[0].timestamp if self.steps else "",
            "end_time": self.steps[-1].timestamp if self.steps else "",
            "steps": [s.to_dict() for s in self.steps],
        }
        json_path = self.session_dir / "session.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Markdown report
        md_path = self.session_dir / "report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Steps Recording — {self.session_id}\n\n")
            f.write(f"**Total steps:** {len(self.steps)}\n")
            if self.steps:
                f.write(f"**Duration:** {self.steps[0].timestamp} → {self.steps[-1].timestamp}\n\n")
            f.write("---\n\n")
            for s in self.steps:
                icon = {"click": "🖱️", "right_click": "🖱️", "middle_click": "🖱️",
                        "keystroke": "⌨️", "typing": "📝"}.get(s.action, "•")
                f.write(f"### Step {s.index}: {icon} {s.action.replace('_',' ').title()}\n\n")
                f.write(f"**Time:** {s.timestamp}  \n")
                f.write(f"**Detail:** {s.detail}  \n")
                f.write(f"**Window:** {s.window['title'][:60]} ({s.window['exe']})  \n")
                f.write(f"**Handle:** hwnd={s.window['hwnd']}, pid={s.window['pid']}, class={s.window['class']}  \n")
                if s.clipboard:
                    f.write(f"**Clipboard:** `{s.clipboard[:80]}`  \n")
                if s.screenshot_path:
                    rel = os.path.relpath(s.screenshot_path, self.session_dir)
                    f.write(f"\n![Step {s.index}]({rel})\n")
                f.write("\n---\n\n")

        return json_path, md_path


# ── Viewer / Presenter ───────────────────────────────────────────────────────
class StepsViewer:
    def __init__(self, root, recorder):
        self.root = root
        self.recorder = recorder
        self.current_step = 0
        self._photo = None  # prevent GC

    def show(self):
        """Open the viewer window."""
        if not self.recorder.steps:
            messagebox.showinfo("Empty", "No steps recorded.", parent=self.root)
            return

        self.win = tk.Toplevel(self.root)
        self.win.title(f"Steps Recording — {self.recorder.session_id} — {len(self.recorder.steps)} steps")
        self.win.configure(bg="#ffffff")

        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        w, h = min(1100, sw - 60), min(760, sh - 80)
        self.win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # ── Top bar ──
        top = tk.Frame(self.win, bg="#2d2740", padx=16, pady=10)
        top.pack(fill="x")

        tk.Label(top, text=f"⏺ Session {self.recorder.session_id}",
                 font=("Consolas", 12, "bold"), fg="#f5c2e7", bg="#2d2740").pack(side="left")
        tk.Label(top, text=f"{len(self.recorder.steps)} steps recorded",
                 font=("Segoe UI", 10), fg="#b4befe", bg="#2d2740").pack(side="left", padx=16)

        # Export buttons
        tk.Button(top, text="📤 Export MD", font=("Segoe UI", 9),
                  fg="#ffffff", bg="#6c5ce7", relief="flat", padx=12,
                  command=self._export_md).pack(side="right", padx=4)
        tk.Button(top, text="📋 Copy JSON", font=("Segoe UI", 9),
                  fg="#ffffff", bg="#89b4fa", relief="flat", padx=12,
                  command=self._copy_json).pack(side="right", padx=4)

        # ── Main split — left: step list, right: detail ──
        split = tk.PanedWindow(self.win, orient="horizontal", bg="#e8e6f0",
                                sashwidth=3)
        split.pack(fill="both", expand=True)

        # Left: step list
        left = tk.Frame(split, bg="#faf9ff", width=300)
        split.add(left, minsize=250)

        # Step list with scrollbar
        list_frame = tk.Frame(left, bg="#faf9ff")
        list_frame.pack(fill="both", expand=True)

        self.step_listbox = tk.Listbox(list_frame, font=("Consolas", 9),
                                         bg="#faf9ff", fg="#2d2740",
                                         selectbackground="#6c5ce7",
                                         selectforeground="#ffffff",
                                         relief="flat", borderwidth=0,
                                         highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical",
                                   command=self.step_listbox.yview)
        self.step_listbox.configure(yscrollcommand=scrollbar.set)
        self.step_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Populate list
        icons = {"click": "🖱", "right_click": "🖱", "middle_click": "🖱",
                 "keystroke": "⌨", "typing": "✏"}
        for s in self.recorder.steps:
            icon = icons.get(s.action, "•")
            line = f" {s.index:3d}  {icon} {s.detail[:45]}"
            self.step_listbox.insert("end", line)

        self.step_listbox.bind("<<ListboxSelect>>", self._on_select)

        # Right: detail panel
        right = tk.Frame(split, bg="#ffffff")
        split.add(right, minsize=500)

        # Screenshot area
        self.img_label = tk.Label(right, bg="#1e1e2e", text="Select a step",
                                   font=("Segoe UI", 11), fg="#666")
        self.img_label.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        # Detail info
        self.detail_frame = tk.Frame(right, bg="#faf9ff", padx=12, pady=10)
        self.detail_frame.pack(fill="x", padx=8, pady=(0, 8))

        self.detail_action = tk.Label(self.detail_frame, text="",
                                       font=("Segoe UI", 11, "bold"),
                                       fg="#2d2740", bg="#faf9ff", anchor="w")
        self.detail_action.pack(fill="x")

        self.detail_text = tk.Label(self.detail_frame, text="",
                                     font=("Segoe UI", 9), fg="#555",
                                     bg="#faf9ff", anchor="w", wraplength=500,
                                     justify="left")
        self.detail_text.pack(fill="x", pady=2)

        self.detail_window = tk.Label(self.detail_frame, text="",
                                       font=("Consolas", 8), fg="#888",
                                       bg="#faf9ff", anchor="w", wraplength=500,
                                       justify="left")
        self.detail_window.pack(fill="x")

        self.detail_clipboard = tk.Label(self.detail_frame, text="",
                                          font=("Consolas", 8), fg="#6c5ce7",
                                          bg="#faf9ff", anchor="w", wraplength=500,
                                          justify="left")
        self.detail_clipboard.pack(fill="x")

        # Navigation bar
        nav = tk.Frame(right, bg="#ffffff", pady=6)
        nav.pack(fill="x", padx=8)

        tk.Button(nav, text="◀ Previous", font=("Segoe UI", 9),
                  relief="flat", bg="#f0eef8", fg="#6c5ce7", padx=14,
                  command=self._prev).pack(side="left")
        tk.Button(nav, text="Next ▶", font=("Segoe UI", 9),
                  relief="flat", bg="#f0eef8", fg="#6c5ce7", padx=14,
                  command=self._next).pack(side="left", padx=4)

        self.step_counter_label = tk.Label(nav, text="",
                                            font=("Segoe UI", 9), fg="#888",
                                            bg="#ffffff")
        self.step_counter_label.pack(side="right")

        # Select first step
        if self.recorder.steps:
            self.step_listbox.selection_set(0)
            self._show_step(0)

    def _on_select(self, event):
        sel = self.step_listbox.curselection()
        if sel:
            self._show_step(sel[0])

    def _show_step(self, idx):
        if idx < 0 or idx >= len(self.recorder.steps):
            return
        self.current_step = idx
        step = self.recorder.steps[idx]

        # Screenshot
        if step.screenshot_path and os.path.exists(step.screenshot_path):
            try:
                img = Image.open(step.screenshot_path)
                # Fit to display area
                max_w, max_h = 700, 420
                img.thumbnail((max_w, max_h), Image.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
                self.img_label.config(image=self._photo, text="")
            except:
                self.img_label.config(image="", text="Screenshot unavailable")
        else:
            self.img_label.config(image="", text="No screenshot")

        # Details
        icons = {"click": "🖱️ Left Click", "right_click": "🖱️ Right Click",
                 "middle_click": "🖱️ Middle Click",
                 "keystroke": "⌨️ Keystroke", "typing": "📝 Typing"}
        self.detail_action.config(text=f"Step {step.index}: {icons.get(step.action, step.action)}")
        self.detail_text.config(text=f"{step.detail}\n"
                                      f"Time: {step.timestamp}\n"
                                      f"Mouse: ({step.mouse_pos[0]}, {step.mouse_pos[1]})")
        self.detail_window.config(
            text=f"Window: {step.window['title'][:60]}\n"
                 f"Process: {step.window['exe']} (PID {step.window['pid']})\n"
                 f"Handle: hwnd={step.window['hwnd']}, class={step.window['class']}\n"
                 f"Rect: {step.window['rect']}")
        if step.clipboard:
            self.detail_clipboard.config(text=f"Clipboard: {step.clipboard[:120]}")
        else:
            self.detail_clipboard.config(text="")

        self.step_counter_label.config(
            text=f"Step {idx + 1} of {len(self.recorder.steps)}")

        # Highlight in listbox
        self.step_listbox.selection_clear(0, "end")
        self.step_listbox.selection_set(idx)
        self.step_listbox.see(idx)

    def _prev(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _next(self):
        if self.current_step < len(self.recorder.steps) - 1:
            self._show_step(self.current_step + 1)

    def _export_md(self):
        if self.recorder.session_dir:
            md_path = self.recorder.session_dir / "report.md"
            if md_path.exists():
                os.startfile(str(md_path))
            else:
                messagebox.showinfo("Not found", "Report not generated yet.",
                                     parent=self.win)

    def _copy_json(self):
        json_path = self.recorder.session_dir / "session.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    self.win.clipboard_clear()
                    self.win.clipboard_append(f.read())
                    messagebox.showinfo("Copied",
                        f"Session JSON ({len(self.recorder.steps)} steps) copied to clipboard.",
                        parent=self.win)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self.win)


# ── Main app with tray ───────────────────────────────────────────────────────
class StepsApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Steps Recorder v{__version__}")
        self.root.configure(bg="#ffffff")
        self.root.withdraw()  # start hidden, tray only

        self.recorder = StepsRecorder()
        self.viewer = StepsViewer(self.root, self.recorder)
        self._setup_tray()
        self._show_control()

    def _setup_tray(self):
        import pystray
        from PIL import Image as PILImage, ImageDraw as PILDraw

        def _make_icon(recording=False):
            img = PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = PILDraw.Draw(img)
            if recording:
                draw.ellipse([8, 8, 56, 56], fill="#e64553")
                draw.ellipse([22, 22, 42, 42], fill="#ffffff")
            else:
                draw.ellipse([8, 8, 56, 56], fill="#888888")
                draw.ellipse([20, 20, 44, 44], outline="#ffffff", width=2)
            return img

        self._tray_icon_idle = _make_icon(False)
        self._tray_icon_rec = _make_icon(True)

        menu = pystray.Menu(
            pystray.MenuItem("⏺ Start Recording", self._tray_start),
            pystray.MenuItem("⏹ Stop & View", self._tray_stop),
            pystray.MenuItem("📂 Browse Sessions", self._tray_browse),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show Controls", self._tray_show),
            pystray.MenuItem("Quit", self._tray_quit),
        )

        self.tray = pystray.Icon("steps", self._tray_icon_idle,
                                  f"Steps Recorder v{__version__}",
                                  menu=menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _update_tray_icon(self, recording):
        try:
            self.tray.icon = self._tray_icon_rec if recording else self._tray_icon_idle
            self.tray.title = ("⏺ RECORDING..." if recording
                               else f"Steps Recorder v{__version__}")
        except:
            pass

    def _tray_start(self):
        self.root.after(0, self._start_recording)

    def _tray_stop(self):
        self.root.after(0, self._stop_and_view)

    def _tray_browse(self):
        os.startfile(str(SESSIONS_DIR))

    def _tray_show(self):
        self.root.after(0, self._show_control)

    def _tray_quit(self):
        if self.recorder.recording:
            self.recorder.stop_session()
        self.tray.stop()
        self.root.after(0, self.root.destroy)

    def _show_control(self):
        """Show a compact control panel."""
        self.root.deiconify()
        self.root.attributes("-topmost", True)

        # Clear existing
        for child in self.root.winfo_children():
            child.destroy()

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = 380, 200
        self.root.geometry(f"{w}x{h}+{sw - w - 20}+{40}")

        # Header
        hdr = tk.Frame(self.root, bg="#2d2740", pady=10, padx=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⏺ Steps Recorder",
                 font=("Segoe UI", 13, "bold"), fg="#f5c2e7",
                 bg="#2d2740").pack(side="left")

        self.status_label = tk.Label(hdr, text="Ready",
                                      font=("Segoe UI", 9), fg="#a6e3a1",
                                      bg="#2d2740")
        self.status_label.pack(side="right")

        body = tk.Frame(self.root, bg="#ffffff", padx=16, pady=14)
        body.pack(fill="both", expand=True)

        self.rec_btn = tk.Button(body, text="⏺  Start Recording",
                    font=("Segoe UI", 12, "bold"), fg="#ffffff", bg="#e64553",
                    activeforeground="#ffffff", activebackground="#d13848",
                    relief="flat", padx=20, pady=8, cursor="hand2",
                    command=self._toggle_recording)
        self.rec_btn.pack(fill="x", pady=(0, 8))

        btn_row = tk.Frame(body, bg="#ffffff")
        btn_row.pack(fill="x")

        tk.Button(btn_row, text="📂 Sessions", font=("Segoe UI", 9),
                  fg="#6c5ce7", bg="#f0eef8", relief="flat", padx=12, pady=4,
                  cursor="hand2",
                  command=lambda: os.startfile(str(SESSIONS_DIR))).pack(side="left")

        self.step_count = tk.Label(btn_row, text="",
                                    font=("Consolas", 9), fg="#888",
                                    bg="#ffffff")
        self.step_count.pack(side="right")

        self._update_step_count()

    def _toggle_recording(self):
        if self.recorder.recording:
            self._stop_and_view()
        else:
            self._start_recording()

    def _start_recording(self):
        self.recorder.start_session()
        self._update_tray_icon(True)
        try:
            self.rec_btn.config(text="⏹  Stop Recording", bg="#888888")
            self.status_label.config(text="⏺ RECORDING", fg="#e64553")
        except:
            pass
        self._update_step_count()

    def _stop_and_view(self):
        if self.recorder.recording:
            self.recorder.stop_session()
        self._update_tray_icon(False)
        try:
            self.rec_btn.config(text="⏺  Start Recording", bg="#e64553")
            self.status_label.config(text="Stopped", fg="#a6e3a1")
        except:
            pass
        self.viewer = StepsViewer(self.root, self.recorder)
        self.viewer.show()

    def _update_step_count(self):
        try:
            if self.recorder.recording:
                n = len(self.recorder.steps)
                self.step_count.config(text=f"{n} steps captured")
                self.root.after(1000, self._update_step_count)
            else:
                n = len(self.recorder.steps)
                self.step_count.config(text=f"{n} steps" if n else "")
        except:
            pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    StepsApp().run()
