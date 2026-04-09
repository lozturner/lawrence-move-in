"""
Lawrence: Move In — AI Timer v1.0.0
Track time spent in LLM chats and other windows. Multiple concurrent timers.
Auto-logs active window. Jump back to any tracked window. Periodic check-ins.

Usage:
  python aitimer.py
  Double-click "Lawrence — AI Timer" desktop shortcut
"""
__version__ = "1.0.0"
import selfclean; selfclean.ensure_single("aitimer.py")

import json, os, subprocess, sys, time, threading, tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from pathlib import Path
from datetime import datetime, timedelta
from collections import OrderedDict
import win32gui, win32process, win32con
import psutil
from PIL import Image, ImageTk, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "aitimer_config.json"
LOG_DIR = SCRIPT_DIR / "aitimer_logs"
LOG_DIR.mkdir(exist_ok=True)

# ── Known LLM / AI window patterns ───────────────────────────────────────────
AI_PATTERNS = [
    "chatgpt", "claude", "gemini", "copilot", "perplexity",
    "bard", "mistral", "groq", "openai", "anthropic",
    "huggingface", "colab", "jupyter", "notebook",
    "ai studio", "playground", "arena", "poe.com",
]

def is_ai_window(title):
    t = title.lower()
    return any(p in t for p in AI_PATTERNS)

def get_fg_info():
    """Get foreground window info."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = ""
        try:
            exe = psutil.Process(pid).name()
        except:
            pass
        return {"hwnd": hwnd, "title": title, "exe": exe, "pid": pid, "class": cls}
    except:
        return {"hwnd": 0, "title": "", "exe": "", "pid": 0, "class": ""}


# ── Timer instance ────────────────────────────────────────────────────────────
class TrackedTimer:
    def __init__(self, name, hwnd=0, title="", exe=""):
        self.id = f"t_{int(time.time()*1000)}"
        self.name = name
        self.hwnd = hwnd
        self.window_title = title
        self.exe = exe
        self.started = datetime.now()
        self.elapsed = 0.0        # seconds
        self.running = True
        self.paused = False
        self.check_interval = 300  # seconds (5 min default)
        self.last_check = time.time()
        self.log = []             # [{time, event, detail}]
        self._add_log("started", f"Timer started for '{name}'")

    def _add_log(self, event, detail=""):
        self.log.append({
            "time": datetime.now().isoformat(),
            "event": event,
            "detail": detail,
        })

    def tick(self, dt):
        if self.running and not self.paused:
            self.elapsed += dt

    def pause(self):
        self.paused = True
        self._add_log("paused")

    def resume(self):
        self.paused = False
        self._add_log("resumed")

    def stop(self):
        self.running = False
        self.paused = False
        self._add_log("stopped", f"Total: {self.format_elapsed()}")

    def format_elapsed(self):
        s = int(self.elapsed)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h > 0:
            return f"{h}h {m:02d}m {sec:02d}s"
        return f"{m}m {sec:02d}s"

    def needs_check(self):
        if not self.running or self.paused:
            return False
        return (time.time() - self.last_check) >= self.check_interval

    def checked(self):
        self.last_check = time.time()
        self._add_log("checked", "Periodic check-in")

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "hwnd": self.hwnd,
            "window_title": self.window_title, "exe": self.exe,
            "started": self.started.isoformat(),
            "elapsed": self.elapsed, "running": self.running,
            "paused": self.paused, "check_interval": self.check_interval,
            "log": self.log,
        }


# ── Main app ─────────────────────────────────────────────────────────────────
class AITimerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"AI Timer v{__version__}")
        self.root.configure(bg="#ffffff")

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = 420, 580
        self.root.geometry(f"{w}x{h}+{sw - w - 20}+{40}")
        self.root.minsize(360, 400)

        self.timers = []          # list of TrackedTimer
        self._timer_widgets = {}  # timer.id -> dict of widgets
        self._active_log = []     # auto-tracked window log
        self._last_fg_title = ""
        self._check_popup = None
        self._lock = threading.Lock()

        self._build_ui()
        self._setup_tray()
        self._tick_loop()
        self._fg_monitor()

    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self.root, bg="#2d2740", padx=14, pady=10)
        hdr.pack(fill="x")

        tk.Label(hdr, text="⏱ AI Timer",
                 font=("Segoe UI", 14, "bold"), fg="#f9e2af",
                 bg="#2d2740").pack(side="left")

        self.active_label = tk.Label(hdr, text="",
                                      font=("Segoe UI", 9), fg="#a6e3a1",
                                      bg="#2d2740")
        self.active_label.pack(side="right")

        # ── Auto-detect bar ──
        detect_bar = tk.Frame(self.root, bg="#fff8e1", padx=14, pady=8)
        detect_bar.pack(fill="x")

        self.detect_label = tk.Label(detect_bar,
                                      text="Watching for AI/LLM windows...",
                                      font=("Segoe UI", 8), fg="#f57f17",
                                      bg="#fff8e1", anchor="w")
        self.detect_label.pack(side="left", fill="x", expand=True)

        tk.Button(detect_bar, text="⏱ Track Current Window",
                  font=("Segoe UI", 8, "bold"), fg="#ffffff", bg="#f57f17",
                  activebackground="#e65100", relief="flat", padx=10, pady=2,
                  cursor="hand2",
                  command=self._track_current).pack(side="right")

        # ── Quick add ──
        add_bar = tk.Frame(self.root, bg="#f8f8fc", padx=14, pady=8)
        add_bar.pack(fill="x")

        self.add_entry = tk.Entry(add_bar, font=("Segoe UI", 10),
                                   relief="flat", bg="#ffffff",
                                   highlightthickness=1,
                                   highlightbackground="#e8e6f0",
                                   highlightcolor="#6c5ce7")
        self.add_entry.pack(side="left", fill="x", expand=True)
        self.add_entry.insert(0, "Timer name...")
        self.add_entry.bind("<FocusIn>", lambda e: (
            self.add_entry.delete(0, "end") if self.add_entry.get() == "Timer name..." else None))
        self.add_entry.bind("<Return>", lambda e: self._add_named())

        tk.Button(add_bar, text="+ Add", font=("Segoe UI", 9, "bold"),
                  fg="#ffffff", bg="#6c5ce7", relief="flat", padx=14, pady=4,
                  cursor="hand2",
                  command=self._add_named).pack(side="right", padx=(8, 0))

        # ── Divider ──
        tk.Frame(self.root, bg="#e8e6f0", height=2).pack(fill="x")

        # ── Timer list (scrollable) ──
        container = tk.Frame(self.root, bg="#ffffff")
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, bg="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.timer_frame = tk.Frame(canvas, bg="#ffffff")

        self.timer_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.timer_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _wheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _wheel)

        # ── Footer ──
        footer = tk.Frame(self.root, bg="#faf9ff", padx=14, pady=8)
        footer.pack(fill="x")

        tk.Button(footer, text="📤 Export Log", font=("Segoe UI", 8),
                  fg="#6c5ce7", bg="#f0eef8", relief="flat", padx=10,
                  cursor="hand2",
                  command=self._export_log).pack(side="left")

        tk.Button(footer, text="🗑 Clear Finished", font=("Segoe UI", 8),
                  fg="#888", bg="#f0f0f5", relief="flat", padx=10,
                  cursor="hand2",
                  command=self._clear_finished).pack(side="left", padx=4)

        self.total_label = tk.Label(footer, text="",
                                     font=("Consolas", 9), fg="#888",
                                     bg="#faf9ff")
        self.total_label.pack(side="right")

    def _track_current(self):
        """Start a timer for the current foreground window."""
        info = get_fg_info()
        title = info["title"]
        if not title or "AI Timer" in title:
            return

        # Don't duplicate
        for t in self.timers:
            if t.running and t.window_title == title:
                self._flash_status(f"Already tracking: {t.name}")
                return

        # Auto-name
        name = title[:40]
        if is_ai_window(title):
            for p in AI_PATTERNS:
                if p in title.lower():
                    name = f"{p.title()} chat"
                    break

        timer = TrackedTimer(name, info["hwnd"], title, info["exe"])
        self.timers.append(timer)
        self._rebuild_timer_list()
        self._flash_status(f"Tracking: {name}")

    def _add_named(self):
        """Add a timer with a custom name, linked to current window."""
        name = self.add_entry.get().strip()
        if not name or name == "Timer name...":
            return

        info = get_fg_info()
        timer = TrackedTimer(name, info["hwnd"], info["title"], info["exe"])
        self.timers.append(timer)
        self.add_entry.delete(0, "end")
        self.add_entry.insert(0, "Timer name...")
        self._rebuild_timer_list()

    def _rebuild_timer_list(self):
        """Redraw all timer cards."""
        for child in self.timer_frame.winfo_children():
            child.destroy()
        self._timer_widgets = {}

        if not self.timers:
            tk.Label(self.timer_frame, text="No timers yet.\n\n"
                     "Click 'Track Current Window' or type a name and hit +",
                     font=("Segoe UI", 10), fg="#aaa", bg="#ffffff",
                     justify="center", pady=40).pack()
            return

        for timer in self.timers:
            self._make_timer_card(timer)

    def _make_timer_card(self, timer):
        """Build a single timer card widget."""
        is_ai = is_ai_window(timer.window_title)

        # Card colours
        if not timer.running:
            border_col = "#ddd"
            bg = "#f8f8f8"
        elif timer.paused:
            border_col = "#f9e2af"
            bg = "#fffdf5"
        elif is_ai:
            border_col = "#cba6f7"
            bg = "#faf5ff"
        else:
            border_col = "#89b4fa"
            bg = "#f5f8ff"

        card = tk.Frame(self.timer_frame, bg=bg, highlightthickness=1,
                        highlightbackground=border_col)
        card.pack(fill="x", padx=12, pady=4)

        # Left accent
        tk.Frame(card, bg=border_col, width=4).pack(side="left", fill="y")

        inner = tk.Frame(card, bg=bg, padx=10, pady=8)
        inner.pack(side="left", fill="both", expand=True)

        # Top row: name + elapsed
        top = tk.Frame(inner, bg=bg)
        top.pack(fill="x")

        name_text = timer.name
        if is_ai:
            name_text = f"🤖 {timer.name}"

        tk.Label(top, text=name_text,
                 font=("Segoe UI", 10, "bold"), fg="#2d2740",
                 bg=bg, anchor="w").pack(side="left")

        elapsed_label = tk.Label(top, text=timer.format_elapsed(),
                                  font=("Consolas", 12, "bold"),
                                  fg="#6c5ce7" if timer.running else "#aaa",
                                  bg=bg)
        elapsed_label.pack(side="right")

        # Status + window
        status = "⏸ Paused" if timer.paused else ("⏹ Done" if not timer.running else "⏱ Running")
        status_color = "#f57f17" if timer.paused else ("#aaa" if not timer.running else "#00b894")

        info_frame = tk.Frame(inner, bg=bg)
        info_frame.pack(fill="x", pady=(2, 0))

        tk.Label(info_frame, text=status,
                 font=("Segoe UI", 8, "bold"), fg=status_color,
                 bg=bg).pack(side="left")

        win_title = timer.window_title[:35] + "…" if len(timer.window_title) > 35 else timer.window_title
        tk.Label(info_frame, text=f"  {timer.exe} — {win_title}",
                 font=("Segoe UI", 8), fg="#888", bg=bg).pack(side="left", padx=4)

        # Button row
        btn_row = tk.Frame(inner, bg=bg)
        btn_row.pack(fill="x", pady=(6, 0))

        if timer.running:
            if timer.paused:
                tk.Button(btn_row, text="▶ Resume", font=("Segoe UI", 8),
                          fg="#ffffff", bg="#00b894", relief="flat", padx=8,
                          cursor="hand2",
                          command=lambda t=timer: self._resume(t)).pack(side="left", padx=(0,4))
            else:
                tk.Button(btn_row, text="⏸ Pause", font=("Segoe UI", 8),
                          fg="#ffffff", bg="#f57f17", relief="flat", padx=8,
                          cursor="hand2",
                          command=lambda t=timer: self._pause(t)).pack(side="left", padx=(0,4))

            tk.Button(btn_row, text="⏹ Stop", font=("Segoe UI", 8),
                      fg="#ffffff", bg="#e64553", relief="flat", padx=8,
                      cursor="hand2",
                      command=lambda t=timer: self._stop(t)).pack(side="left", padx=(0,4))

        # Jump back button (always available)
        tk.Button(btn_row, text="↗ Jump", font=("Segoe UI", 8),
                  fg="#6c5ce7", bg="#f0eef8", relief="flat", padx=8,
                  cursor="hand2",
                  command=lambda t=timer: self._jump(t)).pack(side="left", padx=(0,4))

        # Check interval selector
        if timer.running:
            intervals = {"2m": 120, "5m": 300, "10m": 600, "15m": 900, "30m": 1800, "Off": 0}
            current = "Off"
            for label, secs in intervals.items():
                if secs == timer.check_interval:
                    current = label
                    break

            tk.Label(btn_row, text="Check:", font=("Segoe UI", 7),
                     fg="#888", bg=bg).pack(side="right")

            def _cycle_check(t=timer):
                opts = [120, 300, 600, 900, 1800, 0]
                try:
                    idx = opts.index(t.check_interval)
                except ValueError:
                    idx = -1
                t.check_interval = opts[(idx + 1) % len(opts)]
                self._rebuild_timer_list()

            check_text = f"every {current}" if current != "Off" else "Off"
            tk.Button(btn_row, text=check_text, font=("Segoe UI", 7),
                      fg="#6c5ce7", bg="#f0eef8", relief="flat", padx=6,
                      cursor="hand2",
                      command=_cycle_check).pack(side="right", padx=2)

        # Store refs for live updates
        self._timer_widgets[timer.id] = {
            "elapsed": elapsed_label,
            "card": card,
        }

    def _pause(self, timer):
        timer.pause()
        self._rebuild_timer_list()

    def _resume(self, timer):
        timer.resume()
        self._rebuild_timer_list()

    def _stop(self, timer):
        timer.stop()
        self._rebuild_timer_list()

    def _jump(self, timer):
        """Try to bring the tracked window back to foreground."""
        # First try the original hwnd
        try:
            if timer.hwnd and win32gui.IsWindow(timer.hwnd):
                win32gui.SetForegroundWindow(timer.hwnd)
                timer._add_log("jumped", "Returned to original window")
                return
        except:
            pass

        # Search by title substring
        target = timer.window_title
        if not target:
            return

        found = []
        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                # Match by significant portion of title
                if len(target) > 10 and target[:20].lower() in t.lower():
                    found.append(hwnd)
                elif target.lower() == t.lower():
                    found.append(hwnd)
            return True
        try:
            win32gui.EnumWindows(cb, None)
        except:
            pass

        if found:
            try:
                win32gui.SetForegroundWindow(found[0])
                timer._add_log("jumped", f"Found and focused matching window")
            except:
                pass
        else:
            self._flash_status(f"Window not found: {target[:30]}")

    def _clear_finished(self):
        self.timers = [t for t in self.timers if t.running]
        self._rebuild_timer_list()

    def _export_log(self):
        """Export all timers + auto-log to markdown."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = LOG_DIR / f"timer_log_{ts}.md"

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# AI Timer Log — {ts}\n\n")

            total = sum(t.elapsed for t in self.timers)
            ai_total = sum(t.elapsed for t in self.timers if is_ai_window(t.window_title))
            f.write(f"**Total tracked time:** {int(total//3600)}h {int((total%3600)//60)}m\n")
            f.write(f"**AI/LLM time:** {int(ai_total//3600)}h {int((ai_total%3600)//60)}m\n\n")

            f.write("## Timers\n\n")
            f.write("| Name | Window | Time | Status |\n")
            f.write("|------|--------|------|--------|\n")
            for t in self.timers:
                status = "Running" if t.running and not t.paused else ("Paused" if t.paused else "Done")
                f.write(f"| {t.name} | {t.window_title[:30]} | {t.format_elapsed()} | {status} |\n")

            f.write("\n## Detailed Logs\n\n")
            for t in self.timers:
                f.write(f"### {t.name}\n\n")
                for entry in t.log:
                    f.write(f"- **{entry['time']}** [{entry['event']}] {entry.get('detail','')}\n")
                f.write("\n")

            if self._active_log:
                f.write("## Auto-tracked Window Log\n\n")
                f.write("| Time | Window | Exe |\n")
                f.write("|------|--------|-----|\n")
                for entry in self._active_log[-100:]:
                    f.write(f"| {entry['time']} | {entry['title'][:40]} | {entry['exe']} |\n")

        os.startfile(str(path))
        self._flash_status(f"Exported to {path.name}")

    def _flash_status(self, text):
        try:
            self.active_label.config(text=text)
            self.root.after(4000, lambda: self.active_label.config(text=""))
        except:
            pass

    # ── Background loops ──────────────────────────────────────────────────────
    def _tick_loop(self):
        """Update all timers every second."""
        try:
            for timer in self.timers:
                timer.tick(1.0)
                # Update elapsed display
                if timer.id in self._timer_widgets:
                    try:
                        self._timer_widgets[timer.id]["elapsed"].config(
                            text=timer.format_elapsed())
                    except tk.TclError:
                        pass

                # Check-in popup
                if timer.needs_check():
                    timer.checked()
                    self._show_check_popup(timer)

            # Total in footer
            total = sum(t.elapsed for t in self.timers if t.running)
            running = sum(1 for t in self.timers if t.running and not t.paused)
            if running:
                h, rem = divmod(int(total), 3600)
                m, s = divmod(rem, 60)
                self.total_label.config(text=f"{running} active — {h}h {m:02d}m")
            else:
                self.total_label.config(text="")

            self.root.after(1000, self._tick_loop)
        except tk.TclError:
            pass

    def _fg_monitor(self):
        """Monitor foreground window changes. Auto-detect AI windows."""
        try:
            info = get_fg_info()
            title = info["title"]

            if title and title != self._last_fg_title:
                self._last_fg_title = title
                self._active_log.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "title": title,
                    "exe": info["exe"],
                })
                # Keep log bounded
                if len(self._active_log) > 500:
                    self._active_log = self._active_log[-300:]

                # Auto-detect AI windows
                if is_ai_window(title) and "AI Timer" not in title:
                    already = any(t.running and t.window_title == title for t in self.timers)
                    if not already:
                        self.detect_label.config(
                            text=f"🤖 Detected: {title[:40]}",
                            fg="#e65100")
                    else:
                        self.detect_label.config(
                            text=f"⏱ Tracking: {title[:40]}",
                            fg="#00b894")
                else:
                    self.detect_label.config(
                        text=f"Active: {title[:45]}",
                        fg="#888")

            self.root.after(1000, self._fg_monitor)
        except tk.TclError:
            pass

    def _show_check_popup(self, timer):
        """Show a non-blocking check-in popup for a timer."""
        if self._check_popup:
            try:
                self._check_popup.destroy()
            except:
                pass

        popup = tk.Toplevel(self.root)
        popup.title("Check-in")
        popup.configure(bg="#ffffff")
        popup.attributes("-topmost", True)
        popup.overrideredirect(True)

        sw = popup.winfo_screenwidth()
        w, h = 360, 140
        popup.geometry(f"{w}x{h}+{sw - w - 20}+{20}")

        self._check_popup = popup

        # Card
        accent = "#cba6f7" if is_ai_window(timer.window_title) else "#89b4fa"
        tk.Frame(popup, bg=accent, height=4).pack(fill="x")

        body = tk.Frame(popup, bg="#ffffff", padx=14, pady=10)
        body.pack(fill="both", expand=True)

        tk.Label(body, text=f"⏱ Check-in: {timer.name}",
                 font=("Segoe UI", 11, "bold"), fg="#2d2740",
                 bg="#ffffff").pack(anchor="w")
        tk.Label(body, text=f"Running for {timer.format_elapsed()}. Still going?",
                 font=("Segoe UI", 9), fg="#666", bg="#ffffff").pack(anchor="w", pady=4)

        btn_row = tk.Frame(body, bg="#ffffff")
        btn_row.pack(fill="x", pady=(6, 0))

        def _still_going():
            timer._add_log("confirmed", "User confirmed still active")
            popup.destroy()

        def _done():
            timer.stop()
            popup.destroy()
            self._rebuild_timer_list()

        def _jump_there():
            self._jump(timer)
            popup.destroy()

        tk.Button(btn_row, text="✓ Still going", font=("Segoe UI", 9, "bold"),
                  fg="#ffffff", bg="#00b894", relief="flat", padx=14, pady=4,
                  cursor="hand2", command=_still_going).pack(side="left", padx=(0,4))
        tk.Button(btn_row, text="⏹ Done", font=("Segoe UI", 9),
                  fg="#ffffff", bg="#e64553", relief="flat", padx=10, pady=4,
                  cursor="hand2", command=_done).pack(side="left", padx=(0,4))
        tk.Button(btn_row, text="↗ Jump", font=("Segoe UI", 9),
                  fg="#6c5ce7", bg="#f0eef8", relief="flat", padx=10, pady=4,
                  cursor="hand2", command=_jump_there).pack(side="left")

        # Auto-dismiss after 30s
        popup.after(30000, lambda: (popup.destroy() if popup.winfo_exists() else None))

    # ── Tray ──────────────────────────────────────────────────────────────────
    def _setup_tray(self):
        import pystray

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([6, 6, 58, 58], fill="#f9e2af")
        draw.ellipse([14, 14, 50, 50], fill="#2d2740")
        # Clock hands
        draw.line([(32, 32), (32, 18)], fill="#f9e2af", width=3)
        draw.line([(32, 32), (42, 32)], fill="#f9e2af", width=2)

        menu = pystray.Menu(
            pystray.MenuItem("⏱ Track Current Window", lambda: self.root.after(0, self._track_current)),
            pystray.MenuItem("Show Timer", lambda: self.root.after(0, self._show_window)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📤 Export Log", lambda: self.root.after(0, self._export_log)),
            pystray.MenuItem("Quit", lambda: self._quit()),
        )

        self.tray = pystray.Icon("aitimer", img,
                                  f"AI Timer v{__version__}", menu=menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))

    def _quit(self):
        # Auto-export on quit
        if self.timers:
            try:
                self._export_log()
            except:
                pass
        self.tray.stop()
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.withdraw())
        self.root.mainloop()


if __name__ == "__main__":
    AITimerApp().run()
