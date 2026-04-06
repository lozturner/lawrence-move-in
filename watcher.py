"""
Lawrence: Move In — Watcher v2.0.0
Detects mouse idle → scans desktop → screenshots → Claude Vision deduces.
Raw window list shown separately. Deduction based on what's actually visible.
Voice readout. Thumbs up/down. Export chat. Always on top.
"""

__version__ = "2.0.0"

import base64
import io
import json
import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

import mss
import mss.tools
import win32api
import win32gui
import win32con
import win32process
from PIL import Image

# --- Config ---
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "kidlin_config.json"
CHAT_LOG_DIR = SCRIPT_DIR / "watcher_logs"
IDLE_THRESHOLD = 3.0
COOLDOWN = 45.0
MOVE_TOLERANCE = 5

# --- Palette ---
BG = "#0a0a14"
BG2 = "#12122a"
CARD = "#1a1a3a"
CARD2 = "#141428"
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

SCAN_PROMPT = """You are an expert desktop observer. You have been given a screenshot of the user's desktop taken when they paused (mouse idle).

Analyze what is ACTUALLY VISIBLE on screen. Not just app names — read the content. What tabs are open? What code is shown? What documents? What conversations?

Respond with:

1. **What I can see:** 2-4 bullet points of SPECIFIC things visible on screen. Quote actual text/content you can read. Be precise.

2. **My best guess:** In 1-2 confident sentences, what the user is doing RIGHT NOW based on visual evidence.

3. **Suggested next steps:** 1-2 short actionable suggestions based on what you see.

End with: "Am I right? 👍 👎"

Be specific. "You have VS Code open with a Python file called watcher.py" is good. "You're programming" is useless."""


def load_api_config():
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
                return cfg.get("api_key", ""), cfg.get("model", "claude-sonnet-4-20250514")
    except Exception:
        pass
    return "", "claude-sonnet-4-20250514"


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
        if "Watcher" in title and "v2" in title:
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
        results.append({"title": title[:120], "exe": exe_name, "minimized": is_min})
    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return results


def take_screenshot() -> str:
    """Take a screenshot, resize for API, return base64 JPEG."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]  # all monitors combined
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Resize to max 1200px wide for API (saves tokens, still readable)
    max_w = 1200
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def speak(text):
    """Text-to-speech in background thread."""
    def _speak():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 170)
            voices = engine.getProperty("voices")
            # Try to pick a female voice for variety
            for v in voices:
                if "zira" in v.name.lower() or "female" in v.name.lower():
                    engine.setProperty("voice", v.id)
                    break
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass
    threading.Thread(target=_speak, daemon=True).start()


class Watcher:
    def __init__(self):
        self.root = None
        self._alive = True
        self._drag_x = 0
        self._drag_y = 0
        self._chat = []  # {role, text, time, feedback, voice_text}
        self._last_obs = 0
        self._paused = False
        self._waiting_fb = False
        self._fb_idx = None

    def run(self):
        self.root = tk.Tk()
        self.root.title(f"Watcher v{__version__}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg=BG)

        sw = self.root.winfo_screenwidth()
        w, h = 440, 520
        x = sw - w - 20
        y = 50
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self._build()
        self._make_draggable()
        threading.Thread(target=self._mouse_watcher, daemon=True).start()

        self._add_msg("system",
            "Watcher v2 active. Stop moving your mouse for 3s and I'll "
            "screenshot your desktop, list what's open, and tell you what I see."
        )
        self.root.mainloop()

    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg=BG2, height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self.header = hdr

        tk.Label(hdr, text="Watcher v2", font=("Segoe UI", 9, "bold"),
                 fg=TEAL, bg=BG2).pack(side="left", padx=8)

        self.status_lbl = tk.Label(hdr, text="● Watching", font=("Segoe UI", 7, "bold"),
                                   fg=GREEN, bg=BG2)
        self.status_lbl.pack(side="left", padx=6)

        # Right buttons
        for txt, cmd in [("✕", self._quit), ("Export", self._export),
                         ("Pause", self._toggle_pause)]:
            btn = tk.Label(hdr, text=txt, font=("Segoe UI", 7 if txt != "✕" else 9),
                           fg=DIM, bg="#1a1a3a" if txt != "✕" else BG2,
                           padx=6, pady=1, cursor="hand2")
            btn.pack(side="right", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, c=cmd, b=btn: c(b))
            if txt == "✕":
                btn.bind("<Enter>", lambda e, b=btn: b.config(fg=RED))
                btn.bind("<Leave>", lambda e, b=btn: b.config(fg=DIM))

        # Chat
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=4, pady=2)

        self.canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview, width=5)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)

        self.chat_inner = tk.Frame(self.canvas, bg=BG)
        self.cw = self.canvas.create_window((0, 0), window=self.chat_inner, anchor="nw")
        self.chat_inner.bind("<Configure>",
                             lambda e: self.canvas.config(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self.cw, width=e.width))
        self.canvas.bind("<Enter>",
                         lambda e: self.root.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>",
                         lambda e: self.root.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        try: self.canvas.yview_scroll(-(e.delta // 120), "units")
        except: pass

    def _make_draggable(self):
        def start(e): self._drag_x, self._drag_y = e.x, e.y
        def drag(e):
            self.root.geometry(f"+{self.root.winfo_x() + e.x - self._drag_x}+{self.root.winfo_y() + e.y - self._drag_y}")
        for w in (self.header,) + tuple(self.header.winfo_children()):
            w.bind("<Button-1>", start)
            w.bind("<B1-Motion>", drag)

    # --- Mouse idle detection ---

    def _mouse_watcher(self):
        last_pos = win32api.GetCursorPos()
        idle_start = None
        while self._alive:
            time.sleep(0.3)
            if self._paused: continue
            try: pos = win32api.GetCursorPos()
            except: continue
            if abs(pos[0]-last_pos[0]) > MOVE_TOLERANCE or abs(pos[1]-last_pos[1]) > MOVE_TOLERANCE:
                last_pos = pos
                idle_start = None
            else:
                if idle_start is None:
                    idle_start = time.time()
                elif time.time() - idle_start >= IDLE_THRESHOLD:
                    if time.time() - self._last_obs >= COOLDOWN:
                        self._last_obs = time.time()
                        idle_start = None
                        self.root.after(0, self._observe)

    # --- Observation pipeline ---

    def _observe(self):
        self.status_lbl.config(text="● Scanning...", fg=PEACH)
        now = datetime.now().strftime("%H:%M:%S")

        # Step 1: Window list (immediate, shown raw)
        windows = get_open_windows()
        visible = [w for w in windows if not w["minimized"]]
        minimized = [w for w in windows if w["minimized"]]

        scan_lines = [f"[{now}] Desktop scan — {len(visible)} visible, {len(minimized)} minimized\n"]
        scan_lines.append("VISIBLE:")
        for w in visible:
            scan_lines.append(f"  {w['exe']:.<30s} {w['title'][:60]}")
        if minimized:
            scan_lines.append("MINIMIZED:")
            for w in minimized:
                scan_lines.append(f"  {w['exe']:.<30s} {w['title'][:60]}")

        self._add_msg("scan", "\n".join(scan_lines))

        # Step 2: Screenshot + Vision API (async)
        api_key, model = load_api_config()
        if not api_key:
            self._add_msg("bot", "No API key. Add to kidlin_config.json.")
            self.status_lbl.config(text="● No key", fg=RED)
            return

        self._add_msg("system", "Taking screenshot and sending to Claude Vision...")

        def do_vision():
            try:
                screenshot_b64 = take_screenshot()

                import anthropic
                client = anthropic.Anthropic(api_key=api_key)

                message = client.messages.create(
                    model=model,
                    max_tokens=600,
                    system=SCAN_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": screenshot_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": "What am I doing? Analyze what's actually visible on my screen.",
                            },
                        ],
                    }],
                )

                reply = message.content[0].text

                # Extract voice-friendly text (strip markdown)
                voice_text = reply.replace("**", "").replace("*", "")
                voice_text = voice_text.replace("👍", "thumbs up").replace("👎", "thumbs down")
                # Just read the "best guess" part
                for line in voice_text.split("\n"):
                    if "best guess" in line.lower() or "my best" in line.lower():
                        voice_text = line.strip(": ").strip()
                        break

                self.root.after(0, lambda: self._add_msg("bot", reply,
                                                          with_feedback=True,
                                                          voice_text=voice_text))
                self.root.after(0, lambda: self.status_lbl.config(text="● Watching", fg=GREEN))

            except Exception as e:
                self.root.after(0, lambda: self._add_msg("bot", f"Vision error: {e}"))
                self.root.after(0, lambda: self.status_lbl.config(text="● Error", fg=RED))

        threading.Thread(target=do_vision, daemon=True).start()

    # --- Chat ---

    def _add_msg(self, role, text, with_feedback=False, voice_text=None):
        msg = {"role": role, "text": text, "time": time.time(),
               "feedback": None, "voice_text": voice_text}
        self._chat.append(msg)
        if with_feedback:
            self._waiting_fb = True
            self._fb_idx = len(self._chat) - 1
        self._render()

    def _render(self):
        for w in self.chat_inner.winfo_children():
            w.destroy()
        for i, msg in enumerate(self._chat):
            self._draw_msg(msg)
        if self._waiting_fb and self._fb_idx is not None:
            self._draw_feedback()
        self.root.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def _draw_msg(self, msg):
        role = msg["role"]

        if role == "system":
            f = tk.Frame(self.chat_inner, bg=BG)
            f.pack(fill="x", padx=8, pady=1)
            tk.Label(f, text=msg["text"], font=("Segoe UI", 8),
                     fg=DIM, bg=BG, wraplength=400, justify="left", anchor="w").pack(fill="x")

        elif role == "scan":
            # Raw scan — monospace, distinct colour, collapsible feel
            f = tk.Frame(self.chat_inner, bg=CARD2)
            f.pack(fill="x", padx=8, pady=(4, 2))

            tk.Frame(f, bg=BLUE, width=3).pack(side="left", fill="y")

            inner = tk.Frame(f, bg=CARD2)
            inner.pack(fill="x", padx=6, pady=4)

            tk.Label(inner, text="SCAN", font=("Consolas", 7, "bold"),
                     fg=BLUE, bg=CARD2, anchor="w").pack(fill="x")

            tk.Label(inner, text=msg["text"], font=("Consolas", 8),
                     fg=TEXT, bg=CARD2, wraplength=380, justify="left",
                     anchor="nw").pack(fill="x", pady=(2, 0))

        elif role == "bot":
            f = tk.Frame(self.chat_inner, bg=CARD)
            f.pack(fill="x", padx=(8, 24), pady=(4, 2))

            tk.Frame(f, bg=TEAL, width=3).pack(side="left", fill="y")

            inner = tk.Frame(f, bg=CARD)
            inner.pack(fill="x", padx=8, pady=6)

            # Header row with voice button
            hdr = tk.Frame(inner, bg=CARD)
            hdr.pack(fill="x")

            tk.Label(hdr, text="DEDUCTION", font=("Segoe UI", 7, "bold"),
                     fg=TEAL, bg=CARD).pack(side="left")

            if msg.get("voice_text"):
                voice_btn = tk.Label(hdr, text="🔊 Listen", font=("Segoe UI", 7),
                                     fg=ACCENT, bg=CARD, cursor="hand2")
                voice_btn.pack(side="right")
                vt = msg["voice_text"]
                voice_btn.bind("<Button-1>", lambda e, t=vt: speak(t))

            tk.Label(inner, text=msg["text"], font=("Segoe UI", 9),
                     fg=TEXT, bg=CARD, wraplength=350, justify="left",
                     anchor="nw").pack(fill="x", pady=(4, 0))

            if msg.get("feedback") == "up":
                tk.Label(inner, text="✓ Confirmed", font=("Segoe UI", 7),
                         fg=GREEN, bg=CARD).pack(anchor="w", pady=(2, 0))
            elif msg.get("feedback") == "down":
                tk.Label(inner, text="✗ Corrected", font=("Segoe UI", 7),
                         fg=PEACH, bg=CARD).pack(anchor="w", pady=(2, 0))

        elif role == "user":
            f = tk.Frame(self.chat_inner, bg="#1e2a1e")
            f.pack(fill="x", padx=(24, 8), pady=(2, 4))
            tk.Frame(f, bg=GREEN, width=3).pack(side="right", fill="y")
            inner = tk.Frame(f, bg="#1e2a1e")
            inner.pack(fill="x", padx=8, pady=4)
            tk.Label(inner, text="YOU", font=("Segoe UI", 7, "bold"),
                     fg=GREEN, bg="#1e2a1e").pack(anchor="w")
            tk.Label(inner, text=msg["text"], font=("Segoe UI", 9),
                     fg=TEXT, bg="#1e2a1e", wraplength=340, justify="left",
                     anchor="nw").pack(fill="x")

    def _draw_feedback(self):
        fb = tk.Frame(self.chat_inner, bg=BG)
        fb.pack(fill="x", padx=12, pady=(2, 6))

        for txt, col, vote, hover in [
            (" 👍 Spot on ", GREEN, "up", "#1e3a1e"),
            (" 👎 Not quite ", PEACH, "down", "#3a2a1e"),
        ]:
            btn = tk.Label(fb, text=txt, font=("Segoe UI", 9),
                           fg=col, bg=CARD, padx=8, pady=4, cursor="hand2")
            btn.pack(side="left", padx=(0, 6))
            btn.bind("<Button-1>", lambda e, v=vote: self._feedback(v))
            btn.bind("<Enter>", lambda e, b=btn, h=hover: b.config(bg=h))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=CARD))

        # Also voice the last deduction
        voice_btn = tk.Label(fb, text="🔊 Read aloud", font=("Segoe UI", 8),
                             fg=ACCENT, bg=CARD, padx=8, pady=4, cursor="hand2")
        voice_btn.pack(side="right")
        if self._fb_idx is not None and self._fb_idx < len(self._chat):
            vt = self._chat[self._fb_idx].get("voice_text", "")
            if vt:
                voice_btn.bind("<Button-1>", lambda e, t=vt: speak(t))

    def _feedback(self, vote):
        if self._fb_idx is not None and self._fb_idx < len(self._chat):
            self._chat[self._fb_idx]["feedback"] = vote
        self._waiting_fb = False
        if vote == "up":
            self._fb_idx = None
            self._render()
        else:
            self._fb_idx = None
            self._show_correction()

    def _show_correction(self):
        self._render()
        f = tk.Frame(self.chat_inner, bg=BG)
        f.pack(fill="x", padx=8, pady=(2, 6))

        tk.Label(f, text="What are you actually doing?",
                 font=("Segoe UI", 8, "bold"), fg=PEACH, bg=BG).pack(anchor="w")

        ef = tk.Frame(f, bg=BORDER)
        ef.pack(fill="x", pady=(2, 4))
        entry = tk.Entry(ef, bg=CARD, fg=TEXT, insertbackground=TEXT,
                         font=("Segoe UI", 10), relief="flat")
        entry.pack(fill="x", padx=2, pady=2, ipady=4)
        entry.focus_set()

        def submit(event=None):
            t = entry.get().strip()
            if t: self._add_msg("user", t)
            else: self._render()

        entry.bind("<Return>", submit)
        tk.Label(f, text="Submit", font=("Segoe UI", 8, "bold"),
                 fg=BG, bg=PEACH, padx=10, pady=3, cursor="hand2").pack(anchor="w")
        f.winfo_children()[-1].bind("<Button-1>", lambda e: submit())

        self.root.update_idletasks()
        self.canvas.yview_moveto(1.0)

    # --- Controls ---

    def _toggle_pause(self, btn=None):
        self._paused = not self._paused
        if self._paused:
            self.status_lbl.config(text="● Paused", fg=YELLOW)
            if btn: btn.config(text="Resume")
        else:
            self.status_lbl.config(text="● Watching", fg=GREEN)
            if btn: btn.config(text="Pause")

    def _export(self, btn=None):
        CHAT_LOG_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = CHAT_LOG_DIR / f"watcher_{ts}.md"
        lines = [f"# Watcher Log — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"]
        for msg in self._chat:
            t = datetime.fromtimestamp(msg["time"]).strftime("%H:%M:%S")
            r = msg["role"].upper()
            fb = ""
            if msg.get("feedback") == "up": fb = " ✅"
            elif msg.get("feedback") == "down": fb = " ❌"
            lines.append(f"**[{t}] {r}**{fb}:\n{msg['text']}\n\n")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        self._add_msg("system", f"Exported to {path.name}")

    def _quit(self, btn=None):
        self._alive = False
        try: self.root.destroy()
        except: pass
        os._exit(0)


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("watcher.py")
    Watcher().run()
