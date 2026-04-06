"""
Lawrence: Move In — ShowMe v1.0.0
Behaviour Observer: a companion chatbot that captures how you work.
Screenshots, voice notes, video clips, system snapshots, text notes.
Runs Windows Steps Recorder alongside. Produces a session package for reflection.
"""

__version__ = "1.0.0"

import io
import json
import os
import platform
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
import wave
from datetime import datetime
from pathlib import Path

import cv2
import mss
import mss.tools
import numpy as np
import psutil
import pyaudio
import win32api
import win32gui
import win32process
from PIL import Image, ImageTk

# --- Paths ---
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "showme_config.json"
SESSIONS_DIR = SCRIPT_DIR / "showme_sessions"

# --- Palette (Catppuccin) ---
BG = "#0a0a14"
BG2 = "#12122a"
CARD = "#1a1a3a"
BORDER = "#2a2a50"
TEXT = "#cdd6f4"
DIM = "#5a5a80"
ACCENT = "#cba6f7"
GREEN = "#a6e3a1"
BLUE = "#89b4fa"
PEACH = "#fab387"
RED = "#f38ba8"
TEAL = "#94e2d5"
YELLOW = "#f9e2af"
PINK = "#f5c2e7"

# --- Auto-tag categories ---
TAGS = [
    ("BUG",     RED,    r"\b(bug|crash|error|broken|fix|wrong|fail|issue)\b"),
    ("IDEA",    BLUE,   r"\b(idea|maybe|could|should|what if|how about|feature|add)\b"),
    ("TODO",    PEACH,  r"\b(todo|need to|have to|must|gotta|remember|don't forget)\b"),
    ("FLOW",    GREEN,  r"\b(then|next|after|before|first|always|usually|step)\b"),
    ("TOOL",    TEAL,   r"\b(app|tool|program|browser|editor|vscode|chrome|terminal)\b"),
    ("GRIPE",   PINK,   r"\b(annoying|hate|slow|painful|wish|ugly|clunky|bad)\b"),
    ("THOUGHT", ACCENT, r"\b(think|wonder|feel|interesting|actually|basically|honestly)\b"),
]

import re
TAG_PATTERNS = [(n, c, re.compile(p, re.IGNORECASE)) for n, c, p in TAGS]


def auto_tag(text):
    found = []
    seen = set()
    for name, col, pat in TAG_PATTERNS:
        if name not in seen and pat.search(text):
            found.append((name, col))
            seen.add(name)
    return found[:3]


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {"video_duration": 10, "pos": [None, None], "auto_psr": False}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def get_open_windows():
    results = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or title in ("Program Manager", "Windows Input Experience"):
            return
        rect = win32gui.GetWindowRect(hwnd)
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        if w < 80 or h < 80:
            return
        if "ShowMe" in title:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            handle = win32api.OpenProcess(0x0410, False, pid)
            exe = win32process.GetModuleFileNameEx(handle, 0)
            exe_name = os.path.basename(exe)
            win32api.CloseHandle(handle)
        except Exception:
            exe_name = "unknown"
        is_min = bool(win32gui.IsIconic(hwnd))
        results.append({"title": title[:120], "exe": exe_name, "pid": pid,
                         "minimized": is_min})
    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return results


class ShowMe:
    def __init__(self):
        self.cfg = load_config()
        self._alive = True
        self._drag_x = 0
        self._drag_y = 0
        self._events = []
        self._event_count = 0
        self._start_time = time.time()

        # Voice recording state
        self._recording_voice = False
        self._voice_stream = None
        self._voice_frames = []
        self._pa = None

        # Video recording state
        self._recording_video = False

        # PSR state
        self._psr_proc = None
        self._psr_running = False

        # Session folder
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_dir = SESSIONS_DIR / ts
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "screenshots").mkdir(exist_ok=True)
        (self.session_dir / "voice_notes").mkdir(exist_ok=True)
        (self.session_dir / "video_clips").mkdir(exist_ok=True)
        (self.session_dir / "system_snaps").mkdir(exist_ok=True)
        (self.session_dir / "psr_output").mkdir(exist_ok=True)

        self._timeline_path = self.session_dir / "timeline.jsonl"

    # ── Session logging ──────────────────────────────────────────

    def _log_event(self, etype, data):
        self._event_count += 1
        entry = {
            "n": self._event_count,
            "time": datetime.now().isoformat(),
            "elapsed": round(time.time() - self._start_time, 1),
            "type": etype,
            "data": data,
        }
        self._events.append(entry)
        with open(self._timeline_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    # ── Capture functions ────────────────────────────────────────

    def _take_screenshot(self):
        ts = datetime.now().strftime("%H-%M-%S")
        fname = f"{self._event_count + 1:03d}_{ts}.jpg"
        fpath = self.session_dir / "screenshots" / fname

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        # Save full res
        img.save(str(fpath), format="JPEG", quality=85)

        # Make thumbnail for display
        thumb = img.copy()
        thumb.thumbnail((200, 120), Image.LANCZOS)

        self._log_event("screenshot", {"file": fname})
        self._add_card("screenshot", f"Screenshot saved: {fname}", thumb)

    def _take_system_snap(self):
        ts = datetime.now().strftime("%H-%M-%S")
        fname = f"{self._event_count + 1:03d}_{ts}.json"
        fpath = self.session_dir / "system_snaps" / fname

        fg_hwnd = win32gui.GetForegroundWindow()
        fg_title = win32gui.GetWindowText(fg_hwnd) if fg_hwnd else "None"

        snap = {
            "timestamp": datetime.now().isoformat(),
            "active_window": fg_title,
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory": dict(psutil.virtual_memory()._asdict()),
            "disk": dict(psutil.disk_usage("/")._asdict()),
            "windows": get_open_windows(),
            "system": {
                "platform": platform.platform(),
                "processor": platform.processor(),
                "cpu_count": psutil.cpu_count(),
            },
        }

        fpath.write_text(json.dumps(snap, indent=2, default=str))
        self._log_event("system_snap", {"file": fname, "active": fg_title,
                                         "cpu": snap["cpu_percent"],
                                         "windows": len(snap["windows"])})

        summary = (f"Active: {fg_title[:50]}\n"
                   f"CPU: {snap['cpu_percent']}%  "
                   f"RAM: {snap['memory']['percent']}%\n"
                   f"Windows open: {len(snap['windows'])}")
        self._add_card("system", summary)

    def _start_voice(self):
        if self._recording_voice:
            return
        self._recording_voice = True
        self._voice_frames = []
        self._pa = pyaudio.PyAudio()
        self._voice_stream = self._pa.open(
            format=pyaudio.paInt16, channels=1, rate=16000,
            input=True, frames_per_buffer=1024,
            stream_callback=self._voice_callback,
        )
        self._voice_stream.start_stream()
        self._update_voice_btn()
        self._add_card("voice", "Recording voice note...")

    def _voice_callback(self, in_data, frame_count, time_info, status):
        if self._recording_voice:
            self._voice_frames.append(in_data)
        return (None, pyaudio.paContinue)

    def _stop_voice(self):
        if not self._recording_voice:
            return
        self._recording_voice = False
        if self._voice_stream:
            self._voice_stream.stop_stream()
            self._voice_stream.close()
            self._voice_stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None

        ts = datetime.now().strftime("%H-%M-%S")
        fname = f"{self._event_count + 1:03d}_{ts}.wav"
        fpath = self.session_dir / "voice_notes" / fname

        if self._voice_frames:
            wf = wave.open(str(fpath), "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"".join(self._voice_frames))
            wf.close()

            duration = len(self._voice_frames) * 1024 / 16000
            self._log_event("voice_note", {"file": fname,
                                            "duration_s": round(duration, 1)})
            self._add_card("voice", f"Voice note saved: {fname} ({duration:.1f}s)")
        else:
            self._add_card("voice", "No audio captured")

        self._update_voice_btn()

    def _toggle_voice(self):
        if self._recording_voice:
            self._stop_voice()
        else:
            self._start_voice()

    def _record_video(self):
        if self._recording_video:
            return
        self._recording_video = True
        self._add_card("video", f"Recording {self.cfg['video_duration']}s video clip...")
        threading.Thread(target=self._video_worker, daemon=True).start()

    def _video_worker(self):
        ts = datetime.now().strftime("%H-%M-%S")
        fname = f"{self._event_count + 1:03d}_{ts}.avi"
        fpath = self.session_dir / "video_clips" / fname
        duration = self.cfg.get("video_duration", 10)

        with mss.mss() as sct:
            monitor = sct.monitors[0]
            w, h = monitor["width"], monitor["height"]
            # Scale down for file size
            out_w, out_h = min(w, 1280), min(h, 720)
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(str(fpath), fourcc, 10.0, (out_w, out_h))

            end_time = time.time() + duration
            frames = 0
            while time.time() < end_time and self._alive:
                raw = sct.grab(monitor)
                img = np.array(raw)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                img = cv2.resize(img, (out_w, out_h))
                writer.write(img)
                frames += 1
                time.sleep(0.1)  # ~10 fps

            writer.release()

        self._recording_video = False
        self._log_event("video_clip", {"file": fname, "duration_s": duration,
                                        "frames": frames})
        self.root.after(0, lambda: self._add_card(
            "video", f"Video saved: {fname} ({frames} frames, {duration}s)"))

    def _toggle_psr(self):
        if self._psr_running:
            self._stop_psr()
        else:
            self._start_psr()

    def _start_psr(self):
        output = self.session_dir / "psr_output" / "steps.zip"
        try:
            self._psr_proc = subprocess.Popen(
                ["psr.exe", "/start", "/output", str(output),
                 "/maxsc", "50", "/gui", "0"],
                creationflags=0x00000008,
            )
            self._psr_running = True
            self._log_event("psr", {"action": "start", "output": str(output)})
            self._add_card("psr", "Steps Recorder started")
            self._update_psr_btn()
        except FileNotFoundError:
            self._add_card("psr", "psr.exe not found on this system")
        except Exception as e:
            self._add_card("psr", f"PSR error: {e}")

    def _stop_psr(self):
        if self._psr_proc:
            try:
                subprocess.run(["psr.exe", "/stop"], creationflags=0x00000008)
            except Exception:
                pass
            self._psr_proc = None
        self._psr_running = False
        self._log_event("psr", {"action": "stop"})
        self._add_card("psr", "Steps Recorder stopped")
        self._update_psr_btn()

    # ── UI ───────────────────────────────────────────────────────

    def _add_card(self, etype, text, thumb_img=None):
        """Add an event card to the timeline."""
        now = datetime.now().strftime("%H:%M:%S")
        elapsed = time.time() - self._start_time
        m, s = divmod(int(elapsed), 60)

        icons = {
            "text": ("T", ACCENT),
            "screenshot": ("S", BLUE),
            "voice": ("V", GREEN),
            "video": ("R", PEACH),
            "system": ("X", TEAL),
            "psr": ("P", YELLOW),
            "info": ("i", DIM),
        }
        icon_char, icon_col = icons.get(etype, ("?", DIM))

        card = tk.Frame(self._timeline_inner, bg=CARD, padx=6, pady=4)
        card.pack(fill="x", padx=4, pady=2)

        # Header row
        hdr = tk.Frame(card, bg=CARD)
        hdr.pack(fill="x")

        tk.Label(hdr, text=icon_char, font=("Consolas", 10, "bold"),
                 fg=icon_col, bg=CARD, width=2).pack(side="left")
        tk.Label(hdr, text=f"{now}  +{m:02d}:{s:02d}",
                 font=("Segoe UI", 7), fg=DIM, bg=CARD).pack(side="left", padx=4)

        # Tags for text events
        if etype == "text":
            tags = auto_tag(text)
            for tname, tcol in tags:
                tk.Label(hdr, text=tname, font=("Segoe UI", 6, "bold"),
                         fg=tcol, bg=BORDER, padx=3).pack(side="right", padx=1)

        # Body text
        body = tk.Label(card, text=text, font=("Segoe UI", 8),
                        fg=TEXT, bg=CARD, wraplength=340, justify="left",
                        anchor="w")
        body.pack(fill="x", pady=(2, 0))

        # Thumbnail
        if thumb_img:
            try:
                tk_img = ImageTk.PhotoImage(thumb_img)
                lbl = tk.Label(card, image=tk_img, bg=CARD)
                lbl.image = tk_img  # prevent GC
                lbl.pack(pady=(4, 0))
            except Exception:
                pass

        # Scroll to bottom
        self._timeline_canvas.update_idletasks()
        self._timeline_canvas.yview_moveto(1.0)

        # Update counter
        self._update_status()

    def _update_status(self):
        elapsed = time.time() - self._start_time
        m, s = divmod(int(elapsed), 60)
        h, m = divmod(m, 60)
        count = self._event_count
        self.status_lbl.config(
            text=f"● Session  {h:02d}:{m:02d}:{s:02d}  |  {count} events")

    def _update_voice_btn(self):
        if self._recording_voice:
            self.voice_btn.config(text="Stop", fg=RED)
        else:
            self.voice_btn.config(text="Voice", fg=GREEN)

    def _update_psr_btn(self):
        if self._psr_running:
            self.psr_btn.config(text="PSR Stop", fg=RED)
        else:
            self.psr_btn.config(text="PSR", fg=YELLOW)

    def _on_text_submit(self, event=None):
        text = self._input_var.get().strip()
        if not text:
            return
        self._input_var.set("")
        self._log_event("text_note", {"text": text})
        self._add_card("text", text)

    def _build(self):
        r = self.root

        # ── Header ──
        hdr = tk.Frame(r, bg=BG2, height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self.header = hdr

        tk.Label(hdr, text=f"ShowMe v{__version__}",
                 font=("Segoe UI", 9, "bold"), fg=TEAL, bg=BG2
                 ).pack(side="left", padx=8)

        self.status_lbl = tk.Label(hdr, text="● Session  00:00:00  |  0 events",
                                    font=("Segoe UI", 7, "bold"), fg=GREEN, bg=BG2)
        self.status_lbl.pack(side="left", padx=6)

        # Close button
        close_btn = tk.Label(hdr, text="  \u2715  ", font=("Segoe UI", 9),
                              fg=DIM, bg=BG2, cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self._shutdown())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=RED))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=DIM))

        # ── Timeline (scrollable) ──
        container = tk.Frame(r, bg=BG)
        container.pack(fill="both", expand=True, padx=0, pady=0)

        self._timeline_canvas = tk.Canvas(container, bg=BG, highlightthickness=0,
                                           bd=0)
        scrollbar = tk.Scrollbar(container, orient="vertical",
                                  command=self._timeline_canvas.yview, width=4)
        self._timeline_inner = tk.Frame(self._timeline_canvas, bg=BG)

        self._timeline_inner.bind(
            "<Configure>",
            lambda e: self._timeline_canvas.configure(
                scrollregion=self._timeline_canvas.bbox("all")))

        self._timeline_canvas.create_window((0, 0), window=self._timeline_inner,
                                             anchor="nw",
                                             width=390)
        self._timeline_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self._timeline_canvas.pack(side="left", fill="both", expand=True)

        # Mouse wheel scrolling
        def _on_mousewheel(event):
            self._timeline_canvas.yview_scroll(int(-1 * event.delta / 120), "units")
        self._timeline_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # ── Button bar ──
        btn_bar = tk.Frame(r, bg=BG2, height=32)
        btn_bar.pack(fill="x")
        btn_bar.pack_propagate(False)

        btn_cfg = {"font": ("Segoe UI", 7, "bold"), "bg": CARD,
                   "padx": 6, "pady": 2, "cursor": "hand2", "bd": 0}

        def mkbtn(parent, text, fg, cmd):
            b = tk.Label(parent, text=text, fg=fg, **btn_cfg)
            b.pack(side="left", padx=2, pady=4)
            b.bind("<Button-1>", lambda e: cmd())
            b.bind("<Enter>", lambda e: b.config(bg=BORDER))
            b.bind("<Leave>", lambda e: b.config(bg=CARD))
            return b

        mkbtn(btn_bar, "Screenshot", BLUE, lambda: threading.Thread(
            target=self._take_screenshot, daemon=True).start())
        self.voice_btn = mkbtn(btn_bar, "Voice", GREEN, self._toggle_voice)
        mkbtn(btn_bar, "Video", PEACH, self._record_video)
        mkbtn(btn_bar, "System", TEAL, lambda: threading.Thread(
            target=self._take_system_snap, daemon=True).start())
        self.psr_btn = mkbtn(btn_bar, "PSR", YELLOW, self._toggle_psr)

        # ── Text input ──
        input_frame = tk.Frame(r, bg=BG2, height=36)
        input_frame.pack(fill="x")
        input_frame.pack_propagate(False)

        self._input_var = tk.StringVar()
        entry = tk.Entry(input_frame, textvariable=self._input_var,
                         font=("Segoe UI", 9), fg=TEXT, bg=CARD,
                         insertbackground=TEXT, bd=0, relief="flat")
        entry.pack(fill="x", padx=6, pady=6, expand=True)
        entry.bind("<Return>", self._on_text_submit)
        entry.focus_set()

    def _make_draggable(self):
        def start(e):
            self._drag_x = e.x
            self._drag_y = e.y
        def drag(e):
            x = self.root.winfo_x() + e.x - self._drag_x
            y = self.root.winfo_y() + e.y - self._drag_y
            self.root.geometry(f"+{x}+{y}")

        self.header.bind("<Button-1>", start)
        self.header.bind("<B1-Motion>", drag)
        for child in self.header.winfo_children():
            child.bind("<Button-1>", start)
            child.bind("<B1-Motion>", drag)

    def _tick_status(self):
        """Update status every second."""
        if self._alive:
            self._update_status()
            self.root.after(1000, self._tick_status)

    def _generate_summary(self):
        """Generate session_summary.md on close."""
        elapsed = time.time() - self._start_time
        m, s = divmod(int(elapsed), 60)
        h, m = divmod(m, 60)

        type_counts = {}
        text_notes = []
        for ev in self._events:
            t = ev["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
            if t == "text_note":
                text_notes.append(ev["data"].get("text", ""))

        lines = [
            f"# ShowMe Session Summary",
            f"",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Duration:** {h:02d}:{m:02d}:{s:02d}",
            f"**Total events:** {self._event_count}",
            f"",
            f"## Event Breakdown",
            f"",
        ]
        for t, c in sorted(type_counts.items()):
            lines.append(f"- **{t}**: {c}")

        if text_notes:
            lines.append("")
            lines.append("## Text Notes")
            lines.append("")
            for i, note in enumerate(text_notes, 1):
                tags = auto_tag(note)
                tag_str = " ".join(f"[{n}]" for n, _ in tags)
                lines.append(f"{i}. {note}  {tag_str}")

        lines.append("")
        lines.append("## Files")
        lines.append("")
        for subdir in ["screenshots", "voice_notes", "video_clips",
                       "system_snaps", "psr_output"]:
            p = self.session_dir / subdir
            files = list(p.iterdir()) if p.exists() else []
            if files:
                lines.append(f"### {subdir}/")
                for f in sorted(files):
                    lines.append(f"- `{f.name}`")

        summary_path = self.session_dir / "session_summary.md"
        summary_path.write_text("\n".join(lines), encoding="utf-8")

    def _shutdown(self):
        self._alive = False
        # Stop any active recordings
        if self._recording_voice:
            self._stop_voice()
        if self._psr_running:
            self._stop_psr()

        # Save window position
        try:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            self.cfg["pos"] = [x, y]
            save_config(self.cfg)
        except Exception:
            pass

        # Generate summary
        self._generate_summary()
        self.root.destroy()

    def run(self):
        self.root = tk.Tk()
        self.root.title(f"ShowMe v{__version__}")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg=BG)

        sw = self.root.winfo_screenwidth()
        w, h = 400, 600
        pos = self.cfg.get("pos", [None, None])
        if pos[0] is not None:
            x, y = pos
        else:
            x = sw - w - 20
            y = 50
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self._build()
        self._make_draggable()
        self._tick_status()

        # Welcome card
        self._add_card("info",
            "ShowMe v1 ready. I'm your behaviour observer.\n"
            "Show me how you work — type notes, take screenshots,\n"
            "record voice, capture system state.\n"
            "Everything is timestamped for later reflection.")

        # Auto-start PSR if configured
        if self.cfg.get("auto_psr"):
            self._start_psr()

        self.root.protocol("WM_DELETE_WINDOW", self._shutdown)
        self.root.mainloop()


if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("showme.py")
    ShowMe().run()
