"""
Lawrence: Move In — Scribe v1.1.0
Floating speech-to-text overlay. Always on top.
Listens to mic, shows transcription with auto-tagged categories.
Uses native mic sample rate + resampling for much better pickup.
"""

__version__ = "1.1.0"

import json
import os
import queue
import re
import struct
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import sounddevice as sd
import vosk

# --- Config ---
SCRIPT_DIR = Path(__file__).parent

# Prefer the better model, fall back to small
MODEL_CANDIDATES = [
    SCRIPT_DIR / "vosk-model-en-us-0.22-lgraph",
    SCRIPT_DIR / "vosk-model-small-en-us-0.15",
]
VOSK_RATE = 16000       # vosk wants 16kHz
BLOCK_DURATION = 0.3    # seconds per audio chunk
MAX_SNIPPETS = 12
FADE_AFTER = 20         # seconds before fade starts

# --- Palette ---
BG = "#0a0a14"
BG2 = "#12122a"
TEXT = "#cdd6f4"
DIM = "#5a5a80"
PARTIAL_COL = "#89b4fa"
FINAL_COL = "#a6e3a1"
ACCENT = "#cba6f7"

# --- Auto-tag categories ---
# (tag_name, colour, keyword_patterns)
TAGS = [
    ("BUG",     "#f38ba8", r"\b(bug|crash|error|broken|fix|wrong|fail|issue)\b"),
    ("IDEA",    "#89b4fa", r"\b(idea|maybe|could|should|what if|how about|feature|add)\b"),
    ("TODO",    "#fab387", r"\b(todo|need to|have to|must|gotta|remember|don't forget)\b"),
    ("CODE",    "#a6e3a1", r"\b(function|class|variable|code|script|file|module|import|refactor|api)\b"),
    ("UI",      "#f5c2e7", r"\b(button|layout|design|screen|window|ui|ux|color|font|style|display)\b"),
    ("DEPLOY",  "#94e2d5", r"\b(deploy|ship|release|publish|build|push|production|staging|server)\b"),
    ("PEOPLE",  "#f9e2af", r"\b(meeting|call|email|slack|team|tell|ask|send|message|client)\b"),
    ("THOUGHT", "#b4befe", r"\b(think|wonder|feel|interesting|actually|basically|honestly)\b"),
]

TAG_PATTERNS = [(name, col, re.compile(pat, re.IGNORECASE)) for name, col, pat in TAGS]


def auto_tag(text: str) -> list:
    """Return list of (tag_name, colour) matching the text."""
    found = []
    seen = set()
    for name, col, pattern in TAG_PATTERNS:
        if name not in seen and pattern.search(text):
            found.append((name, col))
            seen.add(name)
    return found[:3]  # max 3 tags per snippet


def resample_to_16k(data: bytes, src_rate: int, channels: int) -> bytes:
    """Downsample int16 PCM to 16kHz mono. Simple linear decimation."""
    if channels > 1:
        # Take first channel only
        samples = struct.unpack(f"<{len(data)//2}h", data)
        samples = samples[::channels]
    else:
        samples = struct.unpack(f"<{len(data)//2}h", data)

    if src_rate == VOSK_RATE:
        return struct.pack(f"<{len(samples)}h", *samples)

    # Decimate
    ratio = src_rate / VOSK_RATE
    out_len = int(len(samples) / ratio)
    out = []
    for i in range(out_len):
        src_idx = int(i * ratio)
        if src_idx < len(samples):
            out.append(samples[src_idx])
    return struct.pack(f"<{len(out)}h", *out)


class Scribe:
    def __init__(self):
        self.root = None
        self.audio_q = queue.Queue()
        self.snippets = []  # list of {text, time, tags, is_final}
        self._alive = True
        self._listening = True
        self._partial = ""
        self._drag_x = 0
        self._drag_y = 0
        self._mic_rate = 44100
        self._mic_channels = 1
        self._mic_device = None

    def run(self):
        # Find model
        model_path = None
        for p in MODEL_CANDIDATES:
            if p.exists():
                model_path = p
                break
        if not model_path:
            print("No vosk model found. Download one to niggly_machine/")
            sys.exit(1)

        print(f"Loading model: {model_path.name}")
        vosk.SetLogLevel(-1)
        self.model = vosk.Model(str(model_path))
        self.recogniser = vosk.KaldiRecognizer(self.model, VOSK_RATE)
        self.recogniser.SetWords(True)

        # Detect mic
        try:
            dev_info = sd.query_devices(sd.default.device[0], "input")
            self._mic_rate = int(dev_info["default_samplerate"])
            self._mic_channels = min(dev_info["max_input_channels"], 2)
            self._mic_device = sd.default.device[0]
            print(f"Mic: {dev_info['name']} @ {self._mic_rate}Hz, {self._mic_channels}ch")
        except Exception as e:
            print(f"Mic detection failed: {e}, using defaults")

        # Start UI
        self.root = tk.Tk()
        self.root.title(f"Scribe v{__version__}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg=BG)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 460, 340
        x = sw - w - 20
        y = sh - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self._build()
        self._make_draggable()

        threading.Thread(target=self._audio_loop, daemon=True).start()
        threading.Thread(target=self._recognition_loop, daemon=True).start()
        self._update_ui()
        self.root.mainloop()

    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg=BG2, height=26)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self.header = hdr

        tk.Label(hdr, text=f"Scribe v{__version__}", font=("Segoe UI", 8, "bold"),
                 fg=ACCENT, bg=BG2).pack(side="left", padx=8)

        self.mic_lbl = tk.Label(hdr, text="● LIVE", font=("Segoe UI", 7, "bold"),
                                fg=FINAL_COL, bg=BG2)
        self.mic_lbl.pack(side="left", padx=6)

        # Close
        close_btn = tk.Label(hdr, text="✕", font=("Segoe UI", 9),
                             fg=DIM, bg=BG2, padx=8, cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self._quit())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg="#f38ba8"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=DIM))

        # Clear
        clear_btn = tk.Label(hdr, text="Clear", font=("Segoe UI", 7),
                             fg=DIM, bg="#1a1a3a", padx=5, pady=1, cursor="hand2")
        clear_btn.pack(side="right", padx=2, pady=2)
        clear_btn.bind("<Button-1>", lambda e: self._clear())

        # Mute
        self.mute_btn = tk.Label(hdr, text="Mute", font=("Segoe UI", 7),
                                 fg=DIM, bg="#1a1a3a", padx=5, pady=1, cursor="hand2")
        self.mute_btn.pack(side="right", padx=2, pady=2)
        self.mute_btn.bind("<Button-1>", lambda e: self._toggle_mute())

        # Snippet area (scrollable)
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=4, pady=(2, 0))

        self.canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview, width=4)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=BG)
        self.cw = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.config(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self.cw, width=e.width))

        # Partial text bar at bottom
        self.partial_frame = tk.Frame(self.root, bg="#0d0d1e", height=28)
        self.partial_frame.pack(fill="x", side="bottom")
        self.partial_frame.pack_propagate(False)

        self.partial_lbl = tk.Label(self.partial_frame, text="", font=("Segoe UI", 9),
                                    fg=PARTIAL_COL, bg="#0d0d1e", anchor="w")
        self.partial_lbl.pack(fill="x", padx=8)

    def _make_draggable(self):
        def start(e):
            self._drag_x, self._drag_y = e.x, e.y
        def drag(e):
            x = self.root.winfo_x() + e.x - self._drag_x
            y = self.root.winfo_y() + e.y - self._drag_y
            self.root.geometry(f"+{x}+{y}")
        for w in (self.header,) + tuple(self.header.winfo_children()):
            w.bind("<Button-1>", start)
            w.bind("<B1-Motion>", drag)

    # --- Audio ---

    def _audio_loop(self):
        block_size = int(self._mic_rate * BLOCK_DURATION)
        try:
            with sd.RawInputStream(
                samplerate=self._mic_rate,
                blocksize=block_size,
                dtype="int16",
                channels=self._mic_channels,
                device=self._mic_device,
                callback=self._audio_cb,
            ):
                while self._alive:
                    time.sleep(0.1)
        except Exception as e:
            print(f"Audio error: {e}")
            # Try to show error in UI
            self.snippets.append({
                "text": f"Mic error: {e}",
                "time": time.time(),
                "tags": [("ERROR", "#f38ba8")],
            })

    def _audio_cb(self, indata, frames, time_info, status):
        if self._listening:
            self.audio_q.put(bytes(indata))

    def _recognition_loop(self):
        while self._alive:
            try:
                data = self.audio_q.get(timeout=0.5)
            except queue.Empty:
                continue

            # Resample to 16kHz mono for vosk
            resampled = resample_to_16k(data, self._mic_rate, self._mic_channels)

            if self.recogniser.AcceptWaveform(resampled):
                result = json.loads(self.recogniser.Result())
                text = result.get("text", "").strip()
                if text and len(text) > 1:
                    tags = auto_tag(text)
                    self.snippets.append({
                        "text": text,
                        "time": time.time(),
                        "tags": tags,
                    })
                    self._partial = ""
                    # Trim
                    if len(self.snippets) > MAX_SNIPPETS * 3:
                        self.snippets = self.snippets[-MAX_SNIPPETS * 2:]
            else:
                partial = json.loads(self.recogniser.PartialResult())
                self._partial = partial.get("partial", "")

    # --- UI update ---

    def _update_ui(self):
        if not self._alive or not self.root:
            return

        try:
            for w in self.inner.winfo_children():
                w.destroy()

            now = time.time()
            visible = []
            for s in self.snippets:
                age = now - s["time"]
                if age < FADE_AFTER * 2.5:
                    visible.append((s, age))

            for s, age in visible[-MAX_SNIPPETS:]:
                self._draw_snippet(s, age)

            # Auto-scroll to bottom
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(1.0)

            # Partial
            partial_display = self._partial
            if len(partial_display) > 60:
                partial_display = "..." + partial_display[-57:]
            self.partial_lbl.config(
                text=f"  {partial_display}" if partial_display else ""
            )

        except Exception:
            pass

        self.root.after(200, self._update_ui)

    def _draw_snippet(self, snippet, age):
        """Draw a single snippet row with tags."""
        row = tk.Frame(self.inner, bg=BG)
        row.pack(fill="x", padx=4, pady=2)

        # Tags on the left
        if snippet["tags"]:
            tag_frame = tk.Frame(row, bg=BG)
            tag_frame.pack(side="left", padx=(0, 6))
            for tag_name, tag_col in snippet["tags"]:
                tag_lbl = tk.Label(
                    tag_frame,
                    text=f" {tag_name} ",
                    font=("Consolas", 7, "bold"),
                    fg="#0a0a14",
                    bg=tag_col,
                    padx=2, pady=0,
                )
                tag_lbl.pack(side="top", pady=1, anchor="w")

        # Text
        if age < 0.6:
            fg = FINAL_COL    # green flash
        elif age < FADE_AFTER:
            fg = TEXT          # normal white
        elif age < FADE_AFTER * 1.5:
            fg = DIM           # fading
        else:
            fg = "#2a2a40"     # nearly invisible

        text_lbl = tk.Label(
            row,
            text=snippet["text"],
            font=("Segoe UI", 10),
            fg=fg, bg=BG,
            wraplength=360, justify="left", anchor="nw",
        )
        text_lbl.pack(side="left", fill="x", expand=True)

        # Timestamp
        ts = time.strftime("%H:%M", time.localtime(snippet["time"]))
        tk.Label(row, text=ts, font=("Segoe UI", 7), fg="#2a2a50", bg=BG).pack(
            side="right", anchor="ne", padx=(4, 0))

    # --- Controls ---

    def _toggle_mute(self):
        self._listening = not self._listening
        if self._listening:
            self.mic_lbl.config(text="● LIVE", fg=FINAL_COL)
            self.mute_btn.config(text="Mute")
        else:
            self.mic_lbl.config(text="● MUTED", fg="#f38ba8")
            self.mute_btn.config(text="Unmute")

    def _clear(self):
        self.snippets.clear()
        self._partial = ""

    def _quit(self):
        self._alive = False
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("scribe.py")
    Scribe().run()
