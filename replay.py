"""
Lawrence: Move In — Replay v1.0.0
Records everything. Replays everything. Answers: "What was I doing?"

RECORDER (background daemon):
  • Screenshot every N seconds
  • Mouse position every 300ms
  • Active window + title every second
  • Running processes snapshot every 10s
  • Clipboard changes
  • Recently modified files in key folders

PLAYER (timeline UI):
  • Scrubber timeline
  • Screenshot playback with mouse cursor trail overlaid
  • Active window timeline strip
  • Process list sidebar
  • Report export (markdown)

Data stored in: niggly_machine/replay_sessions/<date>/
"""
__version__ = "1.0.0"

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path

import mss
import mss.tools
import psutil
import win32api
import win32gui
import win32process
import win32clipboard
import pystray
from PIL import Image, ImageDraw, ImageFont, ImageTk

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
SESSIONS_DIR = SCRIPT_DIR / "replay_sessions"
PYTHONW      = Path(sys.executable).with_name("pythonw.exe")

# ── Palette ──────────────────────────────────────────────────────────────────
BG   = "#0a0a14"; BG2  = "#12122a"; CARD = "#1a1a3a"
CARD_HI = "#252545"; BORDER = "#2a2a50"
TEXT = "#cdd6f4"; DIM  = "#5a5a80"; LAV  = "#b4befe"
GRN  = "#a6e3a1"; PCH  = "#fab387"; MAU  = "#cba6f7"
RED  = "#f38ba8"; TEAL = "#94e2d5"; YEL  = "#f9e2af"
BLUE = "#89b4fa"; PINK = "#f5c2e7"; SKY  = "#89dceb"

# ── Config ───────────────────────────────────────────────────────────────────
DEFAULT_CFG = {
    "screenshot_interval": 10,   # seconds between screenshots
    "mouse_interval": 0.3,      # seconds between mouse position logs
    "window_interval": 1,       # seconds between active window logs
    "process_interval": 10,     # seconds between process snapshots
    "max_session_hours": 8,     # auto-stop after this
    "screenshot_quality": 50,   # JPEG quality (lower = smaller files)
    "screenshot_max_width": 960,
    "watch_folders": [],        # extra folders to scan for file changes
}

CFG_PATH = SCRIPT_DIR / "replay_config.json"

def load_cfg():
    if CFG_PATH.exists():
        try:
            d = json.loads(CFG_PATH.read_text())
            return {**DEFAULT_CFG, **d}
        except: pass
    save_cfg(DEFAULT_CFG)
    return dict(DEFAULT_CFG)

def save_cfg(c):
    CFG_PATH.write_text(json.dumps(c, indent=2), encoding="utf-8")

# ── Data collectors ──────────────────────────────────────────────────────────
SKIP_TITLES  = {"Program Manager", "Windows Input Experience", ""}
SKIP_PROCS   = {"System", "Registry", "smss.exe", "csrss.exe",
                "wininit.exe", "services.exe", "svchost.exe",
                "lsass.exe", "fontdrvhost.exe", "dwm.exe"}

def get_active_window():
    try:
        hwnd  = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        h = win32api.OpenProcess(0x0410, False, pid)
        exe = os.path.basename(win32process.GetModuleFileNameEx(h, 0))
        win32api.CloseHandle(h)
        return {"exe": exe, "title": title[:120], "pid": pid}
    except:
        return {"exe": "unknown", "title": "", "pid": 0}

def get_mouse_pos():
    try:
        x, y = win32api.GetCursorPos()
        return {"x": x, "y": y}
    except:
        return {"x": 0, "y": 0}

def get_visible_windows():
    results = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd): return
        title = win32gui.GetWindowText(hwnd)
        if not title or title in SKIP_TITLES: return
        r = win32gui.GetWindowRect(hwnd)
        if (r[2]-r[0]) < 60 or (r[3]-r[1]) < 60: return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            h = win32api.OpenProcess(0x0410, False, pid)
            exe = os.path.basename(win32process.GetModuleFileNameEx(h, 0))
            win32api.CloseHandle(h)
        except:
            exe = "unknown"
        results.append({"exe": exe, "title": title[:80],
                        "minimized": bool(win32gui.IsIconic(hwnd))})
    try: win32gui.EnumWindows(cb, None)
    except: pass
    return results

def get_processes():
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            name = p.info["name"]
            if name in SKIP_PROCS: continue
            mem = p.info["memory_info"]
            procs.append({
                "pid": p.info["pid"],
                "name": name,
                "mem_mb": round((mem.rss if mem else 0) / 1048576, 1),
            })
        except: pass
    procs.sort(key=lambda x: x["mem_mb"], reverse=True)
    return procs[:30]  # top 30 by memory

def get_clipboard():
    try:
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return data[:500] if data else ""
    except:
        try: win32clipboard.CloseClipboard()
        except: pass
        return ""

def get_recent_files(folders, since_minutes=5):
    """Find files modified in the last N minutes in watched folders."""
    cutoff = time.time() - since_minutes * 60
    results = []
    default_folders = [
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "Documents",
        Path(os.environ.get("USERPROFILE", "")) / "Downloads",
    ]
    for fld in default_folders + [Path(f) for f in folders]:
        if not fld.exists(): continue
        try:
            for f in fld.iterdir():
                if f.is_file() and f.stat().st_mtime > cutoff:
                    results.append({"path": str(f), "modified": f.stat().st_mtime})
        except: pass
    return results[:20]

def take_screenshot(save_path, quality=50, max_w=960):
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[0])
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
    img.save(save_path, format="JPEG", quality=quality)
    return img.size

# ── Session Recorder ─────────────────────────────────────────────────────────
class Recorder:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = SESSIONS_DIR / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "screenshots").mkdir(exist_ok=True)

        self._alive  = True
        self._data   = {
            "session_id": self.session_id,
            "start_time": time.time(),
            "start_dt":   datetime.now().isoformat(),
            "mouse":      [],   # [{t, x, y}]
            "windows":    [],   # [{t, exe, title, pid}]
            "all_windows":[],   # [{t, windows:[...]}]
            "processes":  [],   # [{t, procs:[...]}]
            "screenshots":[],   # [{t, file, w, h}]
            "clipboard":  [],   # [{t, text}]
            "files":      [],   # [{t, files:[...]}]
        }
        self._last_clip = ""
        self._threads = []

    def start(self):
        intervals = [
            ("_rec_mouse",      self.cfg["mouse_interval"]),
            ("_rec_window",     self.cfg["window_interval"]),
            ("_rec_screenshot", self.cfg["screenshot_interval"]),
            ("_rec_processes",  self.cfg["process_interval"]),
            ("_rec_clipboard",  2),
            ("_rec_files",      30),
        ]
        for method_name, interval in intervals:
            t = threading.Thread(target=self._loop,
                                 args=(getattr(self, method_name), interval),
                                 daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self._alive = False
        self._data["end_time"] = time.time()
        self._data["end_dt"]   = datetime.now().isoformat()
        self._data["duration_s"] = self._data["end_time"] - self._data["start_time"]
        self._save()

    def _loop(self, fn, interval):
        max_s = self.cfg.get("max_session_hours", 8) * 3600
        while self._alive:
            if time.time() - self._data["start_time"] > max_s:
                self._alive = False
                break
            try: fn()
            except: pass
            time.sleep(interval)

    def _t(self):
        return round(time.time() - self._data["start_time"], 2)

    def _rec_mouse(self):
        pos = get_mouse_pos()
        self._data["mouse"].append({"t": self._t(), **pos})

    def _rec_window(self):
        w = get_active_window()
        self._data["windows"].append({"t": self._t(), **w})

    def _rec_screenshot(self):
        t  = self._t()
        fn = f"{int(t):06d}.jpg"
        fp = self.session_dir / "screenshots" / fn
        sz = take_screenshot(fp, self.cfg["screenshot_quality"],
                             self.cfg["screenshot_max_width"])
        self._data["screenshots"].append({"t": t, "file": fn, "w": sz[0], "h": sz[1]})
        # Save data incrementally
        self._save()

    def _rec_processes(self):
        procs = get_processes()
        wins  = get_visible_windows()
        self._data["processes"].append({"t": self._t(), "procs": procs})
        self._data["all_windows"].append({"t": self._t(), "windows": wins})

    def _rec_clipboard(self):
        clip = get_clipboard()
        if clip and clip != self._last_clip:
            self._last_clip = clip
            self._data["clipboard"].append({"t": self._t(), "text": clip[:500]})

    def _rec_files(self):
        files = get_recent_files(self.cfg.get("watch_folders", []))
        if files:
            self._data["files"].append({"t": self._t(), "files": files})

    def _save(self):
        p = self.session_dir / "session.json"
        p.write_text(json.dumps(self._data, indent=1, ensure_ascii=False),
                     encoding="utf-8")

# ── Session Player ────────────────────────────────────────────────────────────
class Player:
    def __init__(self, root, session_dir):
        self.root = root
        self.sdir = Path(session_dir)
        self._data = json.loads((self.sdir / "session.json").read_text(encoding="utf-8"))
        self._photos = []
        self._playing = False
        self._speed = 1.0
        self._current_t = 0
        self._duration = self._data.get("duration_s", 0)

        self._build()

    def _build(self):
        self._win = tk.Toplevel(self.root)
        self._win.title(f"Replay — {self.sdir.name}")
        self._win.attributes("-topmost", True)
        self._win.attributes("-alpha", 0.96)
        self._win.configure(bg=BG)

        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        w, h = min(1000, sw - 60), min(700, sh - 60)
        self._win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # Header
        hdr = tk.Frame(self._win, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  ▶ Replay — {self._data.get('start_dt','')[:16]}",
                 font=("Consolas",11,"bold"), fg=LAV, bg=BG2).pack(
                     side="left", padx=8, ipady=8)

        for txt, col, cmd in [
            (" ✕ ", RED, self._close),
            (" 📤 Report ", TEAL, self._export_report),
        ]:
            b = tk.Label(hdr, text=txt, font=("Segoe UI",10),
                         fg=col, bg=BG2, cursor="hand2")
            b.pack(side="right", padx=4)
            b.bind("<Button-1>", lambda e, fn=cmd: fn())

        # Drag
        for w in (hdr,) + tuple(hdr.winfo_children()):
            w.bind("<Button-1>", self._ds)
            w.bind("<B1-Motion>", self._dm)

        # Main content: screenshot left, info right
        body = tk.Frame(self._win, bg=BG)
        body.pack(fill="both", expand=True, padx=8, pady=4)

        # Screenshot display
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)

        self._img_lbl = tk.Label(left, bg="#000", text="No screenshots",
                                 fg=DIM, font=("Segoe UI",11))
        self._img_lbl.pack(fill="both", expand=True, pady=(0,4))

        # Mouse trail overlay canvas
        self._trail_canvas = tk.Canvas(left, bg="#000", highlightthickness=0,
                                       width=400, height=300)
        # We'll overlay this on the image

        # Right panel: window list + process list
        right = tk.Frame(body, bg=CARD, width=260)
        right.pack(side="right", fill="y", padx=(4,0))
        right.pack_propagate(False)

        tk.Label(right, text="Active Window", font=("Consolas",8,"bold"),
                 fg=LAV, bg=CARD).pack(anchor="w", padx=8, pady=(8,2))
        self._win_lbl = tk.Label(right, text="—", font=("Segoe UI",9),
                                 fg=TEXT, bg=CARD, wraplength=240,
                                 justify="left", anchor="nw")
        self._win_lbl.pack(fill="x", padx=8)

        tk.Label(right, text="Clipboard", font=("Consolas",8,"bold"),
                 fg=YEL, bg=CARD).pack(anchor="w", padx=8, pady=(10,2))
        self._clip_lbl = tk.Label(right, text="—", font=("Segoe UI",8),
                                  fg=DIM, bg=CARD, wraplength=240,
                                  justify="left", anchor="nw")
        self._clip_lbl.pack(fill="x", padx=8)

        tk.Label(right, text="Top Processes", font=("Consolas",8,"bold"),
                 fg=GRN, bg=CARD).pack(anchor="w", padx=8, pady=(10,2))
        self._proc_lbl = tk.Label(right, text="—", font=("Consolas",7),
                                  fg=DIM, bg=CARD, wraplength=240,
                                  justify="left", anchor="nw")
        self._proc_lbl.pack(fill="x", padx=8)

        tk.Label(right, text="Files Changed", font=("Consolas",8,"bold"),
                 fg=PCH, bg=CARD).pack(anchor="w", padx=8, pady=(10,2))
        self._file_lbl = tk.Label(right, text="—", font=("Consolas",7),
                                  fg=DIM, bg=CARD, wraplength=240,
                                  justify="left", anchor="nw")
        self._file_lbl.pack(fill="x", padx=8)

        # Timeline bar
        tl = tk.Frame(self._win, bg=BG2)
        tl.pack(fill="x", padx=8, pady=4)

        self._time_lbl = tk.Label(tl, text="00:00 / 00:00",
                                  font=("Consolas",9), fg=DIM, bg=BG2)
        self._time_lbl.pack(side="left", padx=8)

        # Play/pause
        self._play_btn = tk.Label(tl, text="▶", font=("Segoe UI",12,"bold"),
                                  fg=GRN, bg=BG2, cursor="hand2")
        self._play_btn.pack(side="left", padx=4)
        self._play_btn.bind("<Button-1>", lambda _: self._toggle_play())

        # Speed
        for spd, lbl in [(0.5,"½×"),(1,"1×"),(2,"2×"),(4,"4×")]:
            b = tk.Label(tl, text=lbl, font=("Segoe UI",8),
                         fg=DIM, bg=BG2, cursor="hand2", padx=4)
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, s=spd: self._set_speed(s))

        # Scrubber
        self._scrub = tk.Scale(tl, from_=0, to=max(1,int(self._duration)),
                               orient="horizontal", bg=BG2, fg=LAV,
                               troughcolor=CARD, highlightthickness=0,
                               sliderrelief="flat", showvalue=False,
                               command=self._on_scrub)
        self._scrub.pack(side="left", fill="x", expand=True, padx=8)

        # Load first frame
        self._goto(0)

    def _ds(self, e): self._dx, self._dy = e.x, e.y
    def _dm(self, e):
        self._win.geometry(f"+{self._win.winfo_x()+e.x-self._dx}+"
                           f"{self._win.winfo_y()+e.y-self._dy}")

    def _fmt_time(self, s):
        m, sec = divmod(int(s), 60)
        h, m   = divmod(m, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

    def _goto(self, t):
        self._current_t = t
        self._time_lbl.config(
            text=f"{self._fmt_time(t)} / {self._fmt_time(self._duration)}")
        self._scrub.set(int(t))

        # Find nearest screenshot
        shots = self._data.get("screenshots", [])
        best = None
        for s in shots:
            if s["t"] <= t:
                best = s
        if best:
            fp = self.sdir / "screenshots" / best["file"]
            if fp.exists():
                img = Image.open(fp)
                # Draw mouse trail on it
                trail = self._get_mouse_trail(max(0, t-5), t)
                if trail and len(trail) > 1:
                    draw = ImageDraw.Draw(img)
                    sw = img.width / (best.get("w", img.width) or img.width)
                    sh_r = img.height / (best.get("h", img.height) or img.height)
                    # Normalize mouse coords to image space
                    screen_w = win32api.GetSystemMetrics(0)
                    screen_h = win32api.GetSystemMetrics(1)
                    points = []
                    for p in trail:
                        px = int(p["x"] / screen_w * img.width)
                        py = int(p["y"] / screen_h * img.height)
                        points.append((px, py))
                    for i in range(1, len(points)):
                        draw.line([points[i-1], points[i]], fill="#f38ba8", width=2)
                    # Draw current cursor pos
                    if points:
                        cx, cy = points[-1]
                        draw.ellipse([cx-4, cy-4, cx+4, cy+4], fill="#a6e3a1")

                # Resize to fit display
                max_display_w = 700
                if img.width > max_display_w:
                    ratio = max_display_w / img.width
                    img = img.resize((max_display_w, int(img.height * ratio)), Image.LANCZOS)

                photo = ImageTk.PhotoImage(img)
                self._photos = [photo]  # keep reference
                self._img_lbl.config(image=photo, text="")

        # Update active window
        wins = self._data.get("windows", [])
        w_best = None
        for w in wins:
            if w["t"] <= t: w_best = w
        if w_best:
            self._win_lbl.config(text=f"{w_best['exe']}\n{w_best['title']}")

        # Update clipboard
        clips = self._data.get("clipboard", [])
        c_best = None
        for c in clips:
            if c["t"] <= t: c_best = c
        if c_best:
            self._clip_lbl.config(text=c_best["text"][:200])

        # Update processes
        procs = self._data.get("processes", [])
        p_best = None
        for p in procs:
            if p["t"] <= t: p_best = p
        if p_best:
            lines = [f"{p['name']:<20s} {p['mem_mb']:>6.1f}MB"
                     for p in p_best["procs"][:10]]
            self._proc_lbl.config(text="\n".join(lines))

        # Update files
        files = self._data.get("files", [])
        f_best = None
        for f in files:
            if f["t"] <= t: f_best = f
        if f_best:
            names = [os.path.basename(f["path"]) for f in f_best["files"][:8]]
            self._file_lbl.config(text="\n".join(names))

    def _get_mouse_trail(self, t_start, t_end):
        return [m for m in self._data.get("mouse", [])
                if t_start <= m["t"] <= t_end]

    def _on_scrub(self, val):
        self._goto(float(val))

    def _toggle_play(self):
        self._playing = not self._playing
        self._play_btn.config(text="⏸" if self._playing else "▶")
        if self._playing:
            self._play_tick()

    def _set_speed(self, s):
        self._speed = s

    def _play_tick(self):
        if not self._playing:
            return
        self._current_t += 1 * self._speed
        if self._current_t >= self._duration:
            self._playing = False
            self._play_btn.config(text="▶")
            return
        self._goto(self._current_t)
        self._win.after(100, self._play_tick)

    # ── Report ────────────────────────────────────────────────────────────
    def _export_report(self):
        report_path = self.sdir / "report.md"
        lines = [
            f"# Replay Report — {self._data.get('start_dt','')[:16]}\n\n",
            f"**Duration:** {self._fmt_time(self._duration)}\n",
            f"**Screenshots:** {len(self._data.get('screenshots',[]))}\n",
            f"**Mouse positions logged:** {len(self._data.get('mouse',[]))}\n",
            f"**Window switches:** {len(self._data.get('windows',[]))}\n\n",
        ]

        # Window timeline
        lines.append("## Window Timeline\n\n")
        prev_exe = ""
        for w in self._data.get("windows", []):
            if w["exe"] != prev_exe:
                lines.append(f"- **{self._fmt_time(w['t'])}** → {w['exe']}: {w['title'][:60]}\n")
                prev_exe = w["exe"]

        # Clipboard history
        clips = self._data.get("clipboard", [])
        if clips:
            lines.append("\n## Clipboard History\n\n")
            for c in clips:
                short = c["text"][:80].replace("\n"," ")
                lines.append(f"- **{self._fmt_time(c['t'])}** → `{short}`\n")

        # File changes
        all_files = self._data.get("files", [])
        if all_files:
            lines.append("\n## Files Modified\n\n")
            seen = set()
            for entry in all_files:
                for f in entry.get("files", []):
                    bn = os.path.basename(f["path"])
                    if bn not in seen:
                        seen.add(bn)
                        lines.append(f"- {bn}\n")

        # Top processes
        procs = self._data.get("processes", [])
        if procs:
            lines.append("\n## Top Processes (by memory)\n\n")
            last = procs[-1] if procs else {"procs":[]}
            for p in last["procs"][:15]:
                lines.append(f"- {p['name']}: {p['mem_mb']}MB\n")

        report_path.write_text("".join(lines), encoding="utf-8")

        # Copy to clipboard too
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append("".join(lines))
        except: pass

        # Flash status
        tk.Label(self._win, text=f"✓ Report saved: {report_path.name}",
                 font=("Segoe UI",9), fg=GRN, bg=BG2).pack(fill="x")

    def _close(self):
        self._playing = False
        self._win.destroy()


# ── Main App ─────────────────────────────────────────────────────────────────
class ReplayApp:
    def __init__(self):
        self.cfg      = load_cfg()
        self._rec     = None
        self._alive   = True

        self.root = tk.Tk()
        self.root.withdraw()
        self._start_tray()
        self.root.mainloop()

    def _start_recording(self):
        if self._rec:
            return  # already recording
        self._rec = Recorder(self.cfg)
        self._rec.start()

    def _stop_recording(self):
        if not self._rec:
            return
        self._rec.stop()
        session_dir = self._rec.session_dir
        self._rec = None
        return session_dir

    def _open_player(self, session_dir=None):
        if session_dir is None:
            # Find most recent session
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            sessions = sorted(SESSIONS_DIR.iterdir(), reverse=True)
            for s in sessions:
                if (s / "session.json").exists():
                    session_dir = s
                    break
        if session_dir and (session_dir / "session.json").exists():
            Player(self.root, session_dir)
        else:
            # No sessions
            pass

    def _browse_sessions(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        sessions = sorted(
            [s for s in SESSIONS_DIR.iterdir() if (s/"session.json").exists()],
            reverse=True)

        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.configure(bg=BG)
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"350x400+{(sw-350)//2}+{(sh-400)//2}")

        tk.Label(dlg, text="  ▶ Replay Sessions", bg=BG2, fg=LAV,
                 font=("Consolas",11,"bold"), anchor="w").pack(fill="x", ipady=8)

        frame = tk.Frame(dlg, bg=BG)
        frame.pack(fill="both", expand=True, padx=8, pady=4)

        if not sessions:
            tk.Label(frame, text="No sessions recorded yet.\nStart recording from the tray icon.",
                     font=("Segoe UI",10), fg=DIM, bg=BG).pack(expand=True)
        else:
            for s in sessions[:20]:
                try:
                    d = json.loads((s/"session.json").read_text(encoding="utf-8"))
                    dt = d.get("start_dt","")[:16]
                    dur = d.get("duration_s", 0)
                    shots = len(d.get("screenshots",[]))
                    label = f"{dt}  —  {int(dur//60)}min  —  {shots} screenshots"
                except:
                    label = s.name

                row = tk.Label(frame, text=label, font=("Segoe UI",9),
                               fg=TEXT, bg=CARD, anchor="w", padx=10, pady=6,
                               cursor="hand2")
                row.pack(fill="x", pady=1)
                row.bind("<Enter>", lambda e, w=row: w.config(bg=CARD_HI))
                row.bind("<Leave>", lambda e, w=row: w.config(bg=CARD))
                row.bind("<Button-1>",
                    lambda e, sd=s: (dlg.destroy(), self._open_player(sd)))

        cb = tk.Label(dlg, text="Close", bg=BG2, fg=DIM,
                      font=("Segoe UI",8), cursor="hand2", pady=4)
        cb.pack(fill="x")
        cb.bind("<Button-1>", lambda _: dlg.destroy())

    def _start_tray(self):
        img = Image.new("RGBA",(64,64),(0,0,0,0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([4,4,59,59], radius=12, fill=(137,180,250))
        try:    fnt = ImageFont.truetype("consola.ttf",20)
        except: fnt = ImageFont.load_default()
        bb = d.textbbox((0,0),"RP",font=fnt)
        d.text(((64-(bb[2]-bb[0]))//2,(64-(bb[3]-bb[1]))//2),
               "RP", fill="#0a0a14", font=fnt)

        def _rec_label(_):
            return "⏹ Stop Recording" if self._rec else "⏺ Start Recording"

        def _toggle_rec(icon, item):
            if self._rec:
                sd = self._stop_recording()
                self.root.after(0, lambda: self._open_player(sd))
            else:
                self._start_recording()

        def _interval_label(_):
            return f"⏱ Screenshot interval: {self.cfg.get('screenshot_interval',10)}s"

        def _cycle_interval(icon, item):
            opts = [5, 10, 15, 20, 30, 60]
            cur = self.cfg.get("screenshot_interval", 10)
            try: idx = opts.index(cur)
            except: idx = 0
            self.cfg["screenshot_interval"] = opts[(idx+1) % len(opts)]
            save_cfg(self.cfg)

        menu = pystray.Menu(
            pystray.MenuItem(_rec_label, _toggle_rec),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Browse sessions",
                lambda icon, item: self.root.after(0, self._browse_sessions)),
            pystray.MenuItem("Play latest",
                lambda icon, item: self.root.after(0, self._open_player)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_interval_label, _cycle_interval),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",
                lambda icon, item: self._quit(icon)),
        )
        self._tray = pystray.Icon("replay", img, "Replay", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _quit(self, icon=None):
        if self._rec:
            self._rec.stop()
        self._alive = False
        if icon: icon.stop()
        try: self.root.destroy()
        except: pass


if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("replay.py")
    ReplayApp()
