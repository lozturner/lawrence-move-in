"""
Lawrence: Move In -- AI Timer v2.0.0
Live window list with inline timers. Click a window row to start timing it.
Grouped by category. AI/LLM windows highlighted purple. Periodic check-ins.
Export to markdown. System tray.

Usage:
  python aitimer.py
  Double-click "Lawrence -- AI Timer" desktop shortcut
"""
__version__ = "2.0.0"
import selfclean; selfclean.ensure_single("aitimer.py")

import json, os, threading, time, tkinter as tk
from tkinter import ttk
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

import win32gui, win32con, win32process, win32api
import psutil
import pystray
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "aitimer_logs"
LOG_DIR.mkdir(exist_ok=True)

# -- Friendly name mapping (exe -> (display_name, category)) ------------------

FRIENDLY_NAMES = {
    # Browsers
    "chrome.exe": ("Chrome", "Browsers"), "msedge.exe": ("Edge", "Browsers"),
    "firefox.exe": ("Firefox", "Browsers"), "brave.exe": ("Brave", "Browsers"),
    "opera.exe": ("Opera", "Browsers"), "vivaldi.exe": ("Vivaldi", "Browsers"),
    # AI / LLM
    "claude.exe": ("Claude Desktop", "AI / LLM"),
    # Dev Tools
    "Code.exe": ("VS Code", "Dev Tools"), "code.exe": ("VS Code", "Dev Tools"),
    "devenv.exe": ("Visual Studio", "Dev Tools"),
    "WindowsTerminal.exe": ("Terminal", "Dev Tools"), "cmd.exe": ("CMD", "Dev Tools"),
    "powershell.exe": ("PowerShell", "Dev Tools"), "pwsh.exe": ("PowerShell", "Dev Tools"),
    "python.exe": ("Python", "Dev Tools"), "pythonw.exe": ("Python", "Dev Tools"),
    "node.exe": ("Node.js", "Dev Tools"),
    "Figma.exe": ("Figma", "Dev Tools"),
    # Communication
    "Teams.exe": ("Teams", "Communication"), "ms-teams.exe": ("Teams", "Communication"),
    "slack.exe": ("Slack", "Communication"), "Slack.exe": ("Slack", "Communication"),
    "Discord.exe": ("Discord", "Communication"), "discord.exe": ("Discord", "Communication"),
    "OUTLOOK.EXE": ("Outlook", "Communication"), "Outlook.exe": ("Outlook", "Communication"),
    # Office / Notes
    "WINWORD.EXE": ("Word", "Other"), "EXCEL.EXE": ("Excel", "Other"),
    "POWERPNT.EXE": ("PowerPoint", "Other"),
    "Obsidian.exe": ("Obsidian", "Other"), "Notion.exe": ("Notion", "Other"),
    "notepad.exe": ("Notepad", "Other"), "Notepad.exe": ("Notepad", "Other"),
    # Files / System
    "explorer.exe": ("File Explorer", "Other"),
    "Taskmgr.exe": ("Task Manager", "Other"),
    "mstsc.exe": ("Remote Desktop", "Other"),
    "ShadowPC.exe": ("Shadow PC", "Other"),
    "Spotify.exe": ("Spotify", "Other"), "spotify.exe": ("Spotify", "Other"),
    "osk.exe": ("On-Screen Keyboard", "Other"),
}

# Titles to skip entirely
SKIP_TITLES = {"Program Manager", "Windows Input Experience", "", "MSCTFIME UI",
               "Default IME", "Windows Default Lock Screen"}

# AI/LLM detection patterns (matched against window title, lowercase)
AI_PATTERNS = [
    "chatgpt", "claude", "gemini", "copilot", "perplexity",
    "bard", "mistral", "groq", "openai", "anthropic",
    "huggingface", "colab", "jupyter", "ai studio",
]

# Category display order
CATEGORY_ORDER = ["AI / LLM", "Browsers", "Dev Tools", "Communication", "Other"]

# Check-in interval options (label -> seconds, 0 = off)
CHECK_INTERVALS = OrderedDict([
    ("2 min", 120), ("5 min", 300), ("10 min", 600),
    ("15 min", 900), ("30 min", 1800), ("Off", 0),
])
DEFAULT_CHECK_INTERVAL = 300  # 5 min


# -- Helpers -------------------------------------------------------------------

def friendly_name(exe, title=""):
    """Return (display_name, category) for an exe. Falls back to cleaned exe name."""
    if exe in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[exe]
    clean = exe.replace(".exe", "").replace("_", " ").title()
    return clean, "Other"


def is_ai_window(title):
    """Check if a window title matches known AI/LLM patterns."""
    t = title.lower()
    return any(p in t for p in AI_PATTERNS)


def categorize_window(exe, title):
    """Return the category for a window, promoting AI-titled browser tabs to AI/LLM."""
    _, cat = friendly_name(exe, title)
    # If it is a browser but the title matches AI patterns, file under AI/LLM
    if cat == "Browsers" and is_ai_window(title):
        return "AI / LLM"
    return cat


def get_visible_windows():
    """Enumerate all visible, reasonably-sized windows."""
    results = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if win32gui.IsIconic(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title or title in SKIP_TITLES:
            return True
        # Skip tiny windows
        try:
            r = win32gui.GetWindowRect(hwnd)
            if (r[2] - r[0]) < 80 or (r[3] - r[1]) < 50:
                return True
        except Exception:
            return True
        # Get exe
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            h = win32api.OpenProcess(0x0410, False, pid)
            exe = os.path.basename(win32process.GetModuleFileNameEx(h, 0))
            win32api.CloseHandle(h)
        except Exception:
            exe = "unknown"
        results.append({"hwnd": hwnd, "title": title, "exe": exe})
        return True
    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return results


def window_key(info):
    """Unique key for a window entry."""
    return f"{info['exe']}|{info['title'][:80]}"


def format_elapsed(seconds):
    """Format seconds as human-readable elapsed time."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m:02d}m {sec:02d}s"
    return f"{m}m {sec:02d}s"


def make_display_name(exe, title):
    """Build a friendly display string for a window."""
    fname, _ = friendly_name(exe, title)
    # For browsers, append tab title trimmed
    if exe.lower() in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
                        "opera.exe", "vivaldi.exe"):
        # Strip common suffixes
        short = title
        for suffix in (" - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox",
                       " - Brave", " - Opera", " - Vivaldi", " -- Google Chrome",
                       " -- Microsoft Edge"):
            if short.endswith(suffix):
                short = short[:-len(suffix)]
                break
        if len(short) > 50:
            short = short[:47] + "..."
        return f"{fname}: {short}"
    # For other apps, use friendly name + short title context
    if len(title) > 55:
        title = title[:52] + "..."
    # If the friendly name is basically the title, just use friendly name
    if fname.lower() in title.lower() and len(title) < 40:
        return title
    return f"{fname} -- {title}" if title != fname else fname


# -- Timer data ----------------------------------------------------------------

class WindowTimer:
    """Timer state for a single tracked window."""
    def __init__(self, key, display_name, hwnd, exe, title):
        self.key = key
        self.display_name = display_name
        self.hwnd = hwnd
        self.exe = exe
        self.title = title
        self.elapsed = 0.0
        self.running = True
        self.paused = False
        self.started_at = datetime.now()
        self.last_check_time = time.time()
        self.check_interval = DEFAULT_CHECK_INTERVAL
        self.log = [{"time": datetime.now().isoformat(), "event": "started"}]

    def tick(self, dt):
        if self.running and not self.paused:
            self.elapsed += dt

    def toggle_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        event = "paused" if self.paused else "resumed"
        self.log.append({"time": datetime.now().isoformat(), "event": event})

    def stop(self):
        self.running = False
        self.paused = False
        self.log.append({"time": datetime.now().isoformat(), "event": "stopped",
                         "elapsed": format_elapsed(self.elapsed)})

    def needs_check(self):
        if not self.running or self.paused or self.check_interval == 0:
            return False
        return (time.time() - self.last_check_time) >= self.check_interval

    def checked(self):
        self.last_check_time = time.time()


# -- UI colours ----------------------------------------------------------------

BG = "#ffffff"
BG_ALT = "#f8f9fa"
HEADER_BG = "#f0f0f5"
BORDER = "#e0e0e8"
TEXT = "#222222"
TEXT_DIM = "#888888"
PURPLE = "#7c3aed"
PURPLE_LIGHT = "#f3eeff"
PURPLE_BORDER = "#c4b5fd"
BLUE = "#2563eb"
GREEN = "#16a34a"
GREEN_BG = "#f0fdf4"
ORANGE = "#ea580c"
RED = "#dc2626"
YELLOW_ICON = "#f59e0b"
ACTIVE_BG = "#eef2ff"
ACTIVE_BORDER = "#818cf8"
ROW_HOVER = "#f1f5f9"


# -- Main App -----------------------------------------------------------------

class AITimerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"AI Timer v{__version__}")
        self.root.configure(bg=BG)

        sw = self.root.winfo_screenwidth()
        w, h = 420, 580
        self.root.geometry(f"{w}x{h}+{sw - w - 20}+{40}")
        self.root.minsize(380, 450)

        # State
        self.timers = {}         # key -> WindowTimer
        self._last_snapshot = {} # key -> display_name (for diff-based refresh)
        self._row_widgets = {}   # key -> dict of widgets in the row
        self._check_popup = None
        self._check_interval_setting = DEFAULT_CHECK_INTERVAL

        self._build_ui()
        self._setup_tray()

        # Start background loops
        self._tick_loop()
        self._refresh_window_list_loop()

    # -- UI Build --------------------------------------------------------------

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=HEADER_BG, padx=14, pady=10)
        hdr.pack(fill="x")

        tk.Label(hdr, text="AI Timer", font=("Segoe UI", 14, "bold"),
                 fg=TEXT, bg=HEADER_BG).pack(side="left")

        self.status_label = tk.Label(hdr, text="", font=("Segoe UI", 9),
                                     fg=TEXT_DIM, bg=HEADER_BG)
        self.status_label.pack(side="right")

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # Check-in interval bar
        interval_bar = tk.Frame(self.root, bg=BG_ALT, padx=14, pady=6)
        interval_bar.pack(fill="x")

        tk.Label(interval_bar, text="Check-in every:", font=("Segoe UI", 9),
                 fg=TEXT_DIM, bg=BG_ALT).pack(side="left")

        self._interval_var = tk.StringVar(value="5 min")
        for label in CHECK_INTERVALS:
            secs = CHECK_INTERVALS[label]
            rb = tk.Radiobutton(interval_bar, text=label, variable=self._interval_var,
                                value=label, font=("Segoe UI", 8), fg=TEXT,
                                bg=BG_ALT, selectcolor=BG_ALT, activebackground=BG_ALT,
                                indicatoron=0, padx=6, pady=2, relief="flat",
                                overrelief="groove",
                                command=lambda l=label: self._set_check_interval(l))
            rb.pack(side="left", padx=2)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        # Scrollable window list area
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.list_frame = tk.Frame(self.canvas, bg=BG)

        self.list_frame.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._canvas_win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>",
            lambda e: self.canvas.itemconfig(self._canvas_win, width=e.width))
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _wheel(e):
            self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        self.canvas.bind_all("<MouseWheel>", _wheel)

        # Footer
        footer = tk.Frame(self.root, bg=HEADER_BG, padx=14, pady=8)
        footer.pack(fill="x")

        export_btn = tk.Label(footer, text="  Export Log  ", font=("Segoe UI", 9, "bold"),
                              fg=BLUE, bg="#e8edf5", cursor="hand2", padx=8, pady=3)
        export_btn.pack(side="left")
        export_btn.bind("<Button-1>", lambda e: self._export_log())
        export_btn.bind("<Enter>", lambda e: export_btn.configure(bg="#d0d8e8"))
        export_btn.bind("<Leave>", lambda e: export_btn.configure(bg="#e8edf5"))

        self.total_label = tk.Label(footer, text="", font=("Segoe UI", 9),
                                     fg=TEXT_DIM, bg=HEADER_BG)
        self.total_label.pack(side="right")

    # -- Check interval --------------------------------------------------------

    def _set_check_interval(self, label):
        self._check_interval_setting = CHECK_INTERVALS[label]
        # Apply to all running timers
        for t in self.timers.values():
            if t.running:
                t.check_interval = self._check_interval_setting

    # -- Window list -----------------------------------------------------------

    def _refresh_window_list(self):
        """Scan open windows, diff against last snapshot, rebuild if changed."""
        windows = get_visible_windows()

        # Build new snapshot: key -> {display, exe, title, hwnd, category}
        new_snapshot = {}
        for info in windows:
            title = info["title"]
            exe = info["exe"]
            # Skip ourselves
            if f"AI Timer v{__version__}" in title:
                continue
            key = window_key(info)
            display = make_display_name(exe, title)
            cat = categorize_window(exe, title)
            new_snapshot[key] = {
                "display": display, "exe": exe, "title": title,
                "hwnd": info["hwnd"], "category": cat,
            }

        # Diff: only rebuild if windows changed
        old_keys = set(self._last_snapshot.keys())
        new_keys = set(new_snapshot.keys())
        if old_keys == new_keys:
            # Check if display names changed
            changed = False
            for k in new_keys:
                if self._last_snapshot.get(k) != new_snapshot[k].get("display"):
                    changed = True
                    break
            if not changed:
                # Just update hwnd refs for timers (windows can get new handles)
                for k, info in new_snapshot.items():
                    if k in self.timers:
                        self.timers[k].hwnd = info["hwnd"]
                return

        self._last_snapshot = {k: v["display"] for k, v in new_snapshot.items()}
        self._rebuild_list(new_snapshot)

    def _rebuild_list(self, snapshot):
        """Destroy and rebuild the entire window list from snapshot."""
        for child in self.list_frame.winfo_children():
            child.destroy()
        self._row_widgets = {}

        if not snapshot:
            tk.Label(self.list_frame, text="No open windows detected",
                     font=("Segoe UI", 11), fg=TEXT_DIM, bg=BG,
                     pady=40).pack()
            return

        # Group by category
        groups = {}
        for key, info in snapshot.items():
            cat = info["category"]
            if cat not in groups:
                groups[cat] = []
            groups[cat].append((key, info))

        # Sort each group alphabetically by display name
        for cat in groups:
            groups[cat].sort(key=lambda x: x[1]["display"].lower())

        # Render in category order
        for cat in CATEGORY_ORDER:
            if cat not in groups:
                continue
            self._render_group(cat, groups[cat])

        # Any categories not in the predefined order
        for cat in sorted(groups.keys()):
            if cat not in CATEGORY_ORDER:
                self._render_group(cat, groups[cat])

    def _render_group(self, category, items):
        """Render a category header and its window rows."""
        is_ai_group = (category == "AI / LLM")

        # Category header
        hdr_bg = PURPLE_LIGHT if is_ai_group else BG_ALT
        hdr_fg = PURPLE if is_ai_group else TEXT_DIM
        hdr = tk.Frame(self.list_frame, bg=hdr_bg, padx=14, pady=4)
        hdr.pack(fill="x")
        prefix = "* " if is_ai_group else ""
        tk.Label(hdr, text=f"{prefix}{category}", font=("Segoe UI", 9, "bold"),
                 fg=hdr_fg, bg=hdr_bg).pack(side="left")

        # Window rows
        for key, info in items:
            self._render_row(key, info, is_ai_group)

    def _render_row(self, key, info, is_ai_group):
        """Render a single window row. Clickable to start/pause timer."""
        timer = self.timers.get(key)
        has_timer = timer is not None and timer.running

        # Row container
        if has_timer:
            row_bg = PURPLE_LIGHT if is_ai_group else ACTIVE_BG
            border_col = PURPLE_BORDER if is_ai_group else ACTIVE_BORDER
        else:
            row_bg = BG
            border_col = BORDER

        row_outer = tk.Frame(self.list_frame, bg=border_col)
        row_outer.pack(fill="x", padx=8, pady=1)

        row = tk.Frame(row_outer, bg=row_bg, padx=10, pady=6)
        row.pack(fill="both", expand=True, padx=(0, 0), pady=(0, 0))

        # Left accent for AI windows
        if is_ai_group:
            accent = tk.Frame(row_outer, bg=PURPLE, width=3)
            accent.pack(side="left", fill="y")
            accent.lower()  # put behind row

        # Top line: display name
        top = tk.Frame(row, bg=row_bg)
        top.pack(fill="x")

        name_fg = PURPLE if is_ai_group else TEXT
        name_label = tk.Label(top, text=info["display"], font=("Segoe UI", 10),
                              fg=name_fg, bg=row_bg, anchor="w", cursor="hand2")
        name_label.pack(side="left", fill="x", expand=True)

        # Click the name to start/toggle timer
        name_label.bind("<Button-1>", lambda e, k=key, i=info: self._toggle_timer(k, i))

        # Hover effect on the name
        def _enter(e, bg=row_bg):
            name_label.configure(bg=ROW_HOVER)
        def _leave(e, bg=row_bg):
            name_label.configure(bg=bg)
        name_label.bind("<Enter>", _enter)
        name_label.bind("<Leave>", _leave)

        # If timer is active, show elapsed + controls
        if has_timer:
            # Elapsed time (big, bold)
            elapsed_label = tk.Label(top, text=format_elapsed(timer.elapsed),
                                      font=("Segoe UI", 13, "bold"),
                                      fg=PURPLE if is_ai_group else BLUE,
                                      bg=row_bg)
            elapsed_label.pack(side="right")

            # Control row
            ctrl = tk.Frame(row, bg=row_bg)
            ctrl.pack(fill="x", pady=(4, 0))

            # Status indicator
            if timer.paused:
                status_text = "PAUSED"
                status_fg = ORANGE
            else:
                status_text = "RUNNING"
                status_fg = GREEN
            tk.Label(ctrl, text=status_text, font=("Segoe UI", 8, "bold"),
                     fg=status_fg, bg=row_bg).pack(side="left")

            # Pause/Resume button
            if timer.paused:
                pr_btn = tk.Label(ctrl, text="  Resume  ", font=("Segoe UI", 8, "bold"),
                                  fg="#ffffff", bg=GREEN, cursor="hand2", padx=4, pady=1)
            else:
                pr_btn = tk.Label(ctrl, text="  Pause  ", font=("Segoe UI", 8, "bold"),
                                  fg="#ffffff", bg=ORANGE, cursor="hand2", padx=4, pady=1)
            pr_btn.pack(side="left", padx=(8, 4))
            pr_btn.bind("<Button-1>", lambda e, k=key: self._pause_resume(k))

            # Stop button
            stop_btn = tk.Label(ctrl, text="  Stop  ", font=("Segoe UI", 8, "bold"),
                                fg="#ffffff", bg=RED, cursor="hand2", padx=4, pady=1)
            stop_btn.pack(side="left", padx=(0, 4))
            stop_btn.bind("<Button-1>", lambda e, k=key: self._stop_timer(k))

            # Jump button
            jump_btn = tk.Label(ctrl, text="  Jump  ", font=("Segoe UI", 8, "bold"),
                                fg=PURPLE, bg="#ede9fe", cursor="hand2", padx=4, pady=1)
            jump_btn.pack(side="left", padx=(0, 4))
            jump_btn.bind("<Button-1>", lambda e, k=key: self._jump_to(k))

            # Store widget refs for live elapsed updates
            self._row_widgets[key] = {"elapsed": elapsed_label}
        else:
            # Not timed -- show a subtle "click to time" hint
            hint = tk.Label(top, text="click to time", font=("Segoe UI", 8),
                            fg=TEXT_DIM, bg=row_bg)
            hint.pack(side="right")
            self._row_widgets[key] = {}

    # -- Timer actions ---------------------------------------------------------

    def _toggle_timer(self, key, info):
        """Click handler: start a new timer, or pause/resume existing."""
        if key in self.timers and self.timers[key].running:
            self.timers[key].toggle_pause()
        else:
            display = info["display"]
            t = WindowTimer(key, display, info["hwnd"], info["exe"], info["title"])
            t.check_interval = self._check_interval_setting
            self.timers[key] = t
        # Force a list rebuild to show new state
        self._force_rebuild()

    def _pause_resume(self, key):
        if key in self.timers:
            self.timers[key].toggle_pause()
            self._force_rebuild()

    def _stop_timer(self, key):
        if key in self.timers:
            self.timers[key].stop()
            self._force_rebuild()

    def _jump_to(self, key):
        """Bring the tracked window to the foreground."""
        timer = self.timers.get(key)
        if not timer:
            return
        # Try the stored hwnd
        try:
            if timer.hwnd and win32gui.IsWindow(timer.hwnd):
                win32gui.ShowWindow(timer.hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(timer.hwnd)
                return
        except Exception:
            pass
        # Fallback: search by title substring
        target = timer.title
        if not target:
            return
        found = []
        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if target[:25].lower() in t.lower():
                    found.append(hwnd)
            return True
        try:
            win32gui.EnumWindows(cb, None)
        except Exception:
            pass
        if found:
            try:
                win32gui.ShowWindow(found[0], win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(found[0])
            except Exception:
                pass

    def _force_rebuild(self):
        """Force a full list rebuild by clearing the snapshot cache."""
        self._last_snapshot = {}

    # -- Background loops ------------------------------------------------------

    def _tick_loop(self):
        """Tick all running timers every second. Update elapsed labels."""
        try:
            active_count = 0
            total_elapsed = 0.0

            for key, timer in list(self.timers.items()):
                if timer.running:
                    timer.tick(1.0)
                    active_count += (0 if timer.paused else 1)
                    total_elapsed += timer.elapsed

                    # Live-update the elapsed label if visible
                    wid = self._row_widgets.get(key, {})
                    if "elapsed" in wid:
                        try:
                            wid["elapsed"].config(text=format_elapsed(timer.elapsed))
                        except tk.TclError:
                            pass

                    # Check-in popup
                    if timer.needs_check():
                        timer.checked()
                        self._show_check_popup(timer)

            # Update footer totals
            if active_count > 0:
                self.total_label.config(
                    text=f"{active_count} active -- {format_elapsed(total_elapsed)}")
            else:
                running_timers = [t for t in self.timers.values() if t.running]
                if running_timers:
                    self.total_label.config(text="All paused")
                else:
                    self.total_label.config(text="")

            # Update status
            ai_timers = [t for t in self.timers.values()
                         if t.running and is_ai_window(t.title)]
            if ai_timers:
                names = ", ".join(t.display_name[:20] for t in ai_timers[:2])
                self.status_label.config(text=f"AI: {names}", fg=PURPLE)
            elif active_count > 0:
                self.status_label.config(text=f"{active_count} timing", fg=GREEN)
            else:
                self.status_label.config(text="", fg=TEXT_DIM)

            self.root.after(1000, self._tick_loop)
        except tk.TclError:
            pass

    def _refresh_window_list_loop(self):
        """Refresh the window list every 3 seconds (diff-based)."""
        try:
            self._refresh_window_list()
            self.root.after(3000, self._refresh_window_list_loop)
        except tk.TclError:
            pass

    # -- Check-in popup --------------------------------------------------------

    def _show_check_popup(self, timer):
        """Non-blocking check-in popup for a running timer."""
        if self._check_popup:
            try:
                self._check_popup.destroy()
            except Exception:
                pass

        popup = tk.Toplevel(self.root)
        popup.title("Check-in")
        popup.configure(bg=BG)
        popup.attributes("-topmost", True)

        sw = popup.winfo_screenwidth()
        w, h = 380, 150
        popup.geometry(f"{w}x{h}+{sw - w - 20}+{20}")
        popup.resizable(False, False)

        self._check_popup = popup

        is_ai = is_ai_window(timer.title)
        accent = PURPLE if is_ai else BLUE

        # Top accent line
        tk.Frame(popup, bg=accent, height=4).pack(fill="x")

        body = tk.Frame(popup, bg=BG, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        question = f"Still working on {timer.display_name[:35]}?"
        tk.Label(body, text=question, font=("Segoe UI", 11, "bold"),
                 fg=TEXT, bg=BG, wraplength=340, justify="left").pack(anchor="w")

        tk.Label(body, text=f"{format_elapsed(timer.elapsed)} elapsed",
                 font=("Segoe UI", 10), fg=TEXT_DIM, bg=BG).pack(anchor="w", pady=(2, 8))

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x")

        def _still():
            timer.checked()
            popup.destroy()

        def _done():
            timer.stop()
            popup.destroy()
            self._force_rebuild()

        def _jump():
            self._jump_to(timer.key)
            popup.destroy()

        still_btn = tk.Label(btn_row, text="  Still Going  ", font=("Segoe UI", 9, "bold"),
                             fg="#ffffff", bg=GREEN, cursor="hand2", padx=8, pady=4)
        still_btn.pack(side="left", padx=(0, 6))
        still_btn.bind("<Button-1>", lambda e: _still())

        done_btn = tk.Label(btn_row, text="  Done  ", font=("Segoe UI", 9, "bold"),
                            fg="#ffffff", bg=RED, cursor="hand2", padx=8, pady=4)
        done_btn.pack(side="left", padx=(0, 6))
        done_btn.bind("<Button-1>", lambda e: _done())

        jump_btn = tk.Label(btn_row, text="  Jump  ", font=("Segoe UI", 9, "bold"),
                            fg=PURPLE, bg="#ede9fe", cursor="hand2", padx=8, pady=4)
        jump_btn.pack(side="left")
        jump_btn.bind("<Button-1>", lambda e: _jump())

        # Auto-dismiss after 45 seconds
        popup.after(45000, lambda: (popup.destroy() if popup.winfo_exists() else None))

    # -- Export ----------------------------------------------------------------

    def _export_log(self):
        """Export time breakdown to a markdown file."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = LOG_DIR / f"timer_log_{ts}.md"

        all_timers = list(self.timers.values())
        if not all_timers:
            self.status_label.config(text="Nothing to export", fg=ORANGE)
            self.root.after(3000, lambda: self.status_label.config(text="", fg=TEXT_DIM))
            return

        total = sum(t.elapsed for t in all_timers)
        ai_total = sum(t.elapsed for t in all_timers if is_ai_window(t.title))

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# AI Timer Log -- {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(f"**Total tracked time:** {format_elapsed(total)}\n")
            f.write(f"**AI/LLM time:** {format_elapsed(ai_total)}\n\n")

            f.write("## Time Breakdown\n\n")
            f.write("| Window | Category | Time | Status |\n")
            f.write("|--------|----------|------|--------|\n")

            sorted_timers = sorted(all_timers, key=lambda t: t.elapsed, reverse=True)
            for t in sorted_timers:
                cat = categorize_window(t.exe, t.title)
                status = "Running" if (t.running and not t.paused) else (
                    "Paused" if t.paused else "Stopped")
                f.write(f"| {t.display_name[:40]} | {cat} | {format_elapsed(t.elapsed)} | {status} |\n")

            f.write("\n## Event Log\n\n")
            for t in sorted_timers:
                f.write(f"### {t.display_name}\n\n")
                for entry in t.log:
                    f.write(f"- {entry['time']} -- {entry['event']}")
                    if "elapsed" in entry:
                        f.write(f" ({entry['elapsed']})")
                    f.write("\n")
                f.write("\n")

        try:
            os.startfile(str(path))
        except Exception:
            pass
        self.status_label.config(text=f"Exported: {path.name}", fg=GREEN)
        self.root.after(4000, lambda: self.status_label.config(text="", fg=TEXT_DIM))

    # -- System tray -----------------------------------------------------------

    def _setup_tray(self):
        """Yellow clock system tray icon."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Yellow filled circle
        draw.ellipse([4, 4, 60, 60], fill="#f59e0b")
        # Inner dark circle
        draw.ellipse([12, 12, 52, 52], fill="#1e1e2e")
        # Clock hands
        draw.line([(32, 32), (32, 18)], fill="#f59e0b", width=3)
        draw.line([(32, 32), (44, 32)], fill="#f59e0b", width=2)
        # Center dot
        draw.ellipse([29, 29, 35, 35], fill="#f59e0b")

        menu = pystray.Menu(
            pystray.MenuItem("Show AI Timer", lambda: self.root.after(0, self._show_window),
                             default=True),
            pystray.MenuItem("Export Log", lambda: self.root.after(0, self._export_log)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self._quit()),
        )

        self.tray = pystray.Icon("aitimer", img, f"AI Timer v{__version__}", menu=menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))

    def _quit(self):
        # Auto-export on quit if there are timers
        if self.timers:
            try:
                self._export_log()
            except Exception:
                pass
        try:
            self.tray.stop()
        except Exception:
            pass
        self.root.after(0, self.root.destroy)

    # -- Run -------------------------------------------------------------------

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.withdraw())
        self.root.mainloop()


if __name__ == "__main__":
    AITimerApp().run()
