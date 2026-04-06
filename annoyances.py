"""
Lawrence: Move In — Things That Annoy Me v1.0.0
Persistent checklist of computer annoyances. Text, voice, or screenshot input.
Saves to %USERPROFILE%/Desktop/annoyances.md permanently.
System tray icon. Always on top. Exportable.
"""

__version__ = "1.0.0"

import json
import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

# --- Paths ---
SCRIPT_DIR = Path(__file__).parent
USERPROFILE = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
DB_PATH = USERPROFILE / "Desktop" / "annoyances.md"
DATA_PATH = SCRIPT_DIR / "annoyances_data.json"
CONFIG_PATH = SCRIPT_DIR / "kidlin_config.json"  # shared API key

# --- Palette ---
BG = "#0a0a14"
BG2 = "#12122a"
CARD = "#1a1a3a"
BORDER = "#2a2a50"
TEXT = "#cdd6f4"
DIM = "#5a5a80"
ACCENT = "#f38ba8"  # red — annoyances!
GREEN = "#a6e3a1"
BLUE = "#89b4fa"
PEACH = "#fab387"
RED = "#f38ba8"
TEAL = "#94e2d5"
YELLOW = "#f9e2af"
MAUVE = "#cba6f7"


def load_data():
    try:
        if DATA_PATH.exists():
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"items": []}


def save_data(data):
    try:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    # Also write the markdown file to Desktop
    write_markdown(data)


def write_markdown(data):
    """Write the permanent annoyances.md to Desktop."""
    lines = [
        "# Things That Annoy Me About This Computer\n\n",
        f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n",
        f"*{len(data['items'])} items — "
        f"{sum(1 for i in data['items'] if i.get('fixed'))} fixed, "
        f"{sum(1 for i in data['items'] if not i.get('fixed'))} remaining*\n\n",
        "---\n\n",
    ]

    # Group by status
    active = [i for i in data["items"] if not i.get("fixed")]
    fixed = [i for i in data["items"] if i.get("fixed")]

    if active:
        lines.append("## Still Annoying\n\n")
        for item in active:
            sev = item.get("severity", "medium")
            sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
            tags = " ".join(f"`{t}`" for t in item.get("tags", []))
            lines.append(f"- {sev_icon} **{item['text']}**")
            if tags:
                lines.append(f" {tags}")
            if item.get("notes"):
                lines.append(f"\n  > {item['notes']}")
            if item.get("workaround"):
                lines.append(f"\n  > *Workaround: {item['workaround']}*")
            lines.append(f"\n  *Added {item.get('date', '?')} via {item.get('source', '?')}*\n\n")

    if fixed:
        lines.append("## Fixed / Resolved\n\n")
        for item in fixed:
            lines.append(f"- ~~{item['text']}~~")
            if item.get("fix_note"):
                lines.append(f" — {item['fix_note']}")
            lines.append(f"\n  *Fixed {item.get('fixed_date', '?')}*\n\n")

    try:
        with open(DB_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass


def load_api():
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                c = json.load(f)
                return c.get("api_key", ""), c.get("model", "claude-sonnet-4-20250514")
    except Exception:
        pass
    return "", "claude-sonnet-4-20250514"


    # Viewport: 1=full, 2=medium, 3=small, 0=micro (floating icon)
VIEWPORTS = {
    1: {"w": 400, "h": 560, "label": "Full"},
    2: {"w": 320, "h": 380, "label": "Medium"},
    3: {"w": 260, "h": 240, "label": "Small"},
    0: {"w": 48,  "h": 48,  "label": "Micro"},
}


class Annoyances:
    def __init__(self):
        self.root = None
        self.data = load_data()
        self._alive = True
        self._drag_x = 0
        self._drag_y = 0
        self._filter = "all"
        self.tray_icon = None
        self._viewport = 1  # start full
        self._pos = {}  # remember position per viewport

    def run(self):
        threading.Thread(target=self._run_tray, daemon=True).start()

        self.root = tk.Tk()
        self.root.title(f"Annoyances v{__version__}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.configure(bg=BG)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"400x560+{sw//2 - 200}+{sh//2 - 280}")

        self._rebuild_viewport()
        self.root.mainloop()

    # --- Tray ---

    def _make_tray_icon(self):
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([2, 2, size-2, size-2], radius=12, fill=(243, 139, 168))
        try:
            f = ImageFont.truetype("segoeuib.ttf", 20)
        except Exception:
            f = ImageFont.load_default()
        d.text((size//2, size//2), "!!", fill=(10, 10, 22), font=f, anchor="mm")
        return img

    def _run_tray(self):
        def show(icon, item):
            self.root.after(0, self._show_window)

        def quit_app(icon, item):
            self._alive = False
            icon.stop()
            self.root.after(0, self._quit)

        menu = pystray.Menu(
            pystray.MenuItem("Show Annoyances", show, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_app),
        )

        self.tray_icon = pystray.Icon(
            "annoyances", self._make_tray_icon(),
            f"Annoyances v{__version__}", menu)
        self.tray_icon.run()

    def _show_window(self):
        try:
            self.root.deiconify()
            self.root.lift()
        except Exception:
            pass

    # --- Viewports ---

    def _rebuild_viewport(self):
        """Tear down and rebuild UI for current viewport size."""
        # Save current position
        try:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            if x > 0 or y > 0:
                self._pos[self._viewport] = (x, y)
        except Exception:
            pass

        for w in self.root.winfo_children():
            w.destroy()

        vp = VIEWPORTS[self._viewport]
        w, h = vp["w"], vp["h"]

        # Restore saved position or default
        if self._viewport in self._pos:
            px, py = self._pos[self._viewport]
        else:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            if self._viewport == 0:  # micro: bottom-right
                px, py = sw - 68, sh - 100
            else:
                px, py = sw // 2 - w // 2, sh // 2 - h // 2

        self.root.geometry(f"{w}x{h}+{px}+{py}")

        if self._viewport == 0:
            self._build_micro()
        else:
            self._build()
            self._render_items()

        self._make_draggable()

    def _cycle_viewport(self):
        """Cycle: 1 → 2 → 3 → 0 → 1"""
        cycle = [1, 2, 3, 0]
        idx = cycle.index(self._viewport) if self._viewport in cycle else 0
        self._viewport = cycle[(idx + 1) % len(cycle)]
        self._rebuild_viewport()

    def _set_viewport(self, v):
        self._viewport = v
        self._rebuild_viewport()

    def _build_micro(self):
        """Micro mode: just a floating red !! icon. Click to expand."""
        self.root.configure(bg="")
        self.root.attributes("-alpha", 0.9)
        self.header = self.root  # for draggable

        micro = tk.Canvas(self.root, width=44, height=44, bg=BG, highlightthickness=0)
        micro.pack(fill="both", expand=True)

        # Draw circle
        micro.create_oval(2, 2, 42, 42, fill="#f38ba8", outline="#f38ba8")
        micro.create_text(22, 18, text="!!", font=("Segoe UI", 14, "bold"),
                          fill="#0a0a14")

        # Count badge
        active_n = sum(1 for i in self.data["items"] if not i.get("fixed"))
        if active_n > 0:
            micro.create_oval(28, 28, 44, 44, fill="#f9e2af", outline="#0a0a14")
            micro.create_text(36, 36, text=str(active_n), font=("Segoe UI", 8, "bold"),
                              fill="#0a0a14")

        micro.bind("<Button-1>", lambda e: self._set_viewport(1))
        micro.bind("<Button-3>", lambda e: self._cycle_viewport())

    # --- UI ---

    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg=BG2, height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self.header = hdr

        vp_label = VIEWPORTS[self._viewport]["label"]
        title = "!!" if self._viewport == 3 else "!! Things That Annoy Me"
        tk.Label(hdr, text=title, font=("Segoe UI", 9, "bold"),
                 fg=ACCENT, bg=BG2).pack(side="left", padx=8)

        # Right buttons
        close_btn = tk.Label(hdr, text="✕", font=("Segoe UI", 9),
                             fg=DIM, bg=BG2, padx=6, cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self._quit())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=RED))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=DIM))

        min_btn = tk.Label(hdr, text="—", font=("Segoe UI", 10),
                           fg=DIM, bg=BG2, padx=4, cursor="hand2")
        min_btn.pack(side="right")
        min_btn.bind("<Button-1>", lambda e: self.root.withdraw())

        # Viewport cycle button
        vp_btn = tk.Label(hdr, text=f"[{vp_label}]", font=("Segoe UI", 7),
                          fg=BLUE, bg=BG2, padx=4, cursor="hand2")
        vp_btn.pack(side="right")
        vp_btn.bind("<Button-1>", lambda e: self._cycle_viewport())

        # === Input area (hidden on Small viewport) ===
        if self._viewport in (1, 2):
            input_frame = tk.Frame(self.root, bg=BG)
            input_frame.pack(fill="x", padx=6, pady=(6, 2))

            if self._viewport == 1:
                tk.Label(input_frame, text="What's annoying you?",
                         font=("Segoe UI", 9, "bold"), fg=RED, bg=BG).pack(anchor="w")

            entry_border = tk.Frame(input_frame, bg=BORDER)
            entry_border.pack(fill="x", pady=(2, 0))

            h = 2 if self._viewport == 1 else 1
            self.input_text = tk.Text(entry_border, height=h, bg=CARD, fg=TEXT,
                                      insertbackground=TEXT, font=("Segoe UI", 10 if self._viewport == 1 else 9),
                                      relief="flat", wrap="word", padx=6, pady=4)
            self.input_text.pack(fill="x", padx=1, pady=1)
            self.input_text.bind("<Control-Return>", lambda e: self._add_from_text())

            btn_row = tk.Frame(input_frame, bg=BG)
            btn_row.pack(fill="x", pady=(3, 0))

            add_btn = tk.Label(btn_row, text="Add", font=("Segoe UI", 8, "bold"),
                               fg=BG, bg=RED, padx=12, pady=3, cursor="hand2")
            add_btn.pack(side="left")
            add_btn.bind("<Button-1>", lambda e: self._add_from_text())

            if self._viewport == 1:
                voice_btn = tk.Label(btn_row, text="Voice", font=("Segoe UI", 8),
                                     fg=BLUE, bg=CARD, padx=8, pady=3, cursor="hand2")
                voice_btn.pack(side="left", padx=4)
                voice_btn.bind("<Button-1>", lambda e: self._add_from_voice())

                screenshot_btn = tk.Label(btn_row, text="Screenshot", font=("Segoe UI", 8),
                                          fg=PEACH, bg=CARD, padx=8, pady=3, cursor="hand2")
                screenshot_btn.pack(side="left", padx=0)
                screenshot_btn.bind("<Button-1>", lambda e: self._add_from_screenshot())
        else:
            # Small viewport: no input area, just a dummy for the text field reference
            self.input_text = None

        # === Filter / stats row ===
        filter_row = tk.Frame(self.root, bg=BG)
        filter_row.pack(fill="x", padx=8, pady=(4, 2))

        active_n = sum(1 for i in self.data["items"] if not i.get("fixed"))
        fixed_n = sum(1 for i in self.data["items"] if i.get("fixed"))

        if self._viewport == 3:
            self.stats_lbl = tk.Label(filter_row, text=f"{active_n} active",
                                      font=("Segoe UI", 7), fg=DIM, bg=BG)
        else:
            self.stats_lbl = tk.Label(filter_row,
                                      text=f"{len(self.data['items'])} total | {active_n} active | {fixed_n} fixed",
                                      font=("Segoe UI", 7), fg=DIM, bg=BG)
        self.stats_lbl.pack(side="left")

        for txt, filt, col in [("All", "all", DIM), ("Active", "active", RED), ("Fixed", "fixed", GREEN)]:
            fb = tk.Label(filter_row, text=txt, font=("Segoe UI", 7),
                          fg=col, bg=CARD if self._filter == filt.lower() else BG,
                          padx=4 if self._viewport == 3 else 6, pady=1, cursor="hand2")
            fb.pack(side="right", padx=1)
            fb.bind("<Button-1>", lambda e, f=filt: self._set_filter(f))

        # === Items list ===
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=4, pady=2)

        self.canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview, width=5)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=BG)
        self.cw = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.config(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self.cw, width=e.width))
        self.canvas.bind("<Enter>",
                         lambda e: self.root.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>",
                         lambda e: self.root.unbind_all("<MouseWheel>"))

        # Bottom bar (full + medium only)
        if self._viewport in (1, 2):
            bottom = tk.Frame(self.root, bg=BG2, height=22)
            bottom.pack(fill="x", side="bottom")
            bottom.pack_propagate(False)

            open_md = tk.Label(bottom, text=f"Open {DB_PATH.name}", font=("Segoe UI", 7),
                               fg=BLUE, bg=BG2, cursor="hand2")
            open_md.pack(side="left", padx=8)
            open_md.bind("<Button-1>", lambda e: os.startfile(str(DB_PATH)))

            export_btn = tk.Label(bottom, text="Export", font=("Segoe UI", 7),
                                  fg=PEACH, bg=BG2, cursor="hand2")
            export_btn.pack(side="right", padx=8)
            export_btn.bind("<Button-1>", lambda e: self._export())

    def _wheel(self, e):
        try: self.canvas.yview_scroll(-(e.delta // 120), "units")
        except: pass

    def _make_draggable(self):
        def start(e): self._drag_x, self._drag_y = e.x, e.y
        def drag(e):
            self.root.geometry(
                f"+{self.root.winfo_x()+e.x-self._drag_x}"
                f"+{self.root.winfo_y()+e.y-self._drag_y}")
        for w in (self.header,) + tuple(self.header.winfo_children()):
            w.bind("<Button-1>", start)
            w.bind("<B1-Motion>", drag)

    # === ADD METHODS ===

    def _add_from_text(self):
        if not self.input_text: return
        text = self.input_text.get("1.0", "end").strip()
        if not text: return
        self.input_text.delete("1.0", "end")
        self._add_item(text, source="typed")

    def _add_from_voice(self):
        """Record a short voice clip via vosk, transcribe, add."""
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", "🎤 Listening for 5 seconds...")
        self.root.update()

        def do_record():
            try:
                import sounddevice as sd
                import vosk
                import json as jn

                model_path = None
                for p in [SCRIPT_DIR / "vosk-model-en-us-0.22-lgraph",
                          SCRIPT_DIR / "vosk-model-small-en-us-0.15"]:
                    if p.exists():
                        model_path = p
                        break
                if not model_path:
                    self.root.after(0, lambda: self._set_input("No vosk model found"))
                    return

                vosk.SetLogLevel(-1)
                model = vosk.Model(str(model_path))
                rec = vosk.KaldiRecognizer(model, 16000)

                audio = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype="int16")
                sd.wait()

                rec.AcceptWaveform(audio.tobytes())
                result = jn.loads(rec.Result())
                text = result.get("text", "").strip()

                if text:
                    self.root.after(0, lambda: self._set_input(""))
                    self.root.after(0, lambda: self._add_item(text, source="voice"))
                else:
                    self.root.after(0, lambda: self._set_input("Didn't catch that. Try again."))

            except Exception as e:
                self.root.after(0, lambda: self._set_input(f"Voice error: {e}"))

        threading.Thread(target=do_record, daemon=True).start()

    def _add_from_screenshot(self):
        """Take screenshot, send to Claude Vision to describe annoyance."""
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", "📸 Screenshotting...")
        self.root.update()

        def do_screenshot():
            try:
                import mss
                import base64, io
                from PIL import Image as PILImage

                with mss.mss() as sct:
                    raw = sct.grab(sct.monitors[0])
                    img = PILImage.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

                max_w = 1200
                if img.width > max_w:
                    ratio = max_w / img.width
                    img = img.resize((max_w, int(img.height * ratio)), PILImage.LANCZOS)

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=75)
                b64 = base64.b64encode(buf.getvalue()).decode()

                api_key, model = load_api()
                if not api_key:
                    self.root.after(0, lambda: self._set_input("No API key for vision"))
                    return

                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                msg = client.messages.create(
                    model=model, max_tokens=200,
                    system="Look at this screenshot. The user says something on screen is annoying them. Describe what you see that might be the annoyance in 1-2 sentences. Be specific about what app/window/element looks problematic. Reply with just the annoyance description.",
                    messages=[{"role": "user", "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                        {"type": "text", "text": "What on my screen is annoying? Describe it as an annoyance list item."},
                    ]}],
                )
                text = msg.content[0].text.strip()
                self.root.after(0, lambda: self._set_input(""))
                self.root.after(0, lambda: self._add_item(text, source="screenshot"))

            except Exception as e:
                self.root.after(0, lambda: self._set_input(f"Screenshot error: {e}"))

        threading.Thread(target=do_screenshot, daemon=True).start()

    def _set_input(self, text):
        if not self.input_text: return
        self.input_text.delete("1.0", "end")
        if text:
            self.input_text.insert("1.0", text)

    def _add_item(self, text, source="typed"):
        item = {
            "text": text,
            "source": source,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "severity": "medium",
            "tags": [],
            "notes": "",
            "workaround": "",
            "fixed": False,
            "fixed_date": "",
            "fix_note": "",
        }
        self.data["items"].insert(0, item)
        save_data(self.data)
        self._render_items()

    # === RENDER ===

    def _set_filter(self, f):
        self._filter = f
        self._rebuild_viewport()

    def _render_items(self):
        for w in self.inner.winfo_children():
            w.destroy()

        items = self.data["items"]
        if self._filter == "active":
            items = [i for i in items if not i.get("fixed")]
        elif self._filter == "fixed":
            items = [i for i in items if i.get("fixed")]

        if not items:
            tk.Label(self.inner, text="Nothing here yet. Add your first annoyance!",
                     font=("Segoe UI", 10), fg=DIM, bg=BG).pack(pady=30)
            return

        for item in items:
            self._draw_item(item)

        # Update stats
        active_n = sum(1 for i in self.data["items"] if not i.get("fixed"))
        fixed_n = sum(1 for i in self.data["items"] if i.get("fixed"))
        self.stats_lbl.config(
            text=f"{len(self.data['items'])} total | {active_n} active | {fixed_n} fixed")

        self.root.update_idletasks()

    def _draw_item(self, item):
        fixed = item.get("fixed", False)
        sev = item.get("severity", "medium")
        sev_col = {"critical": RED, "high": PEACH, "medium": YELLOW, "low": GREEN}.get(sev, DIM)
        vp = self._viewport

        frame = tk.Frame(self.inner, bg=CARD)
        frame.pack(fill="x", padx=4, pady=1 if vp == 3 else 2)

        tk.Frame(frame, bg=sev_col if not fixed else GREEN, width=3 if vp == 3 else 4).pack(side="left", fill="y")

        inner = tk.Frame(frame, bg=CARD)
        inner.pack(fill="x", padx=4 if vp == 3 else 8, pady=3 if vp == 3 else 5)

        # Top: checkbox + text
        top = tk.Frame(inner, bg=CARD)
        top.pack(fill="x")

        check_txt = "☑" if fixed else "☐"
        check_col = GREEN if fixed else DIM
        check_size = 10 if vp == 3 else 12
        check = tk.Label(top, text=check_txt, font=("Segoe UI", check_size),
                         fg=check_col, bg=CARD, cursor="hand2")
        check.pack(side="left", padx=(0, 4))
        check.bind("<Button-1>", lambda e, i=item: self._toggle_fixed(i))

        txt_fg = DIM if fixed else TEXT
        txt_size = 8 if vp == 3 else (9 if vp == 2 else 10)
        txt_font = ("Segoe UI", txt_size, "overstrike") if fixed else ("Segoe UI", txt_size)
        wrap = 180 if vp == 3 else (240 if vp == 2 else 300)
        tk.Label(top, text=item["text"], font=txt_font, fg=txt_fg, bg=CARD,
                 wraplength=wrap, justify="left", anchor="nw").pack(side="left", fill="x", expand=True)

        # Severity badge (always shown)
        tk.Label(top, text=f" {sev[0].upper()} " if vp == 3 else f" {sev.upper()} ",
                 font=("Consolas", 5 if vp == 3 else 6, "bold"),
                 fg="#0a0a14", bg=sev_col).pack(side="right")

        # === Medium and Full get extras ===
        if vp >= 2:
            # Tags
            tags = item.get("tags", [])
            if tags:
                meta_row = tk.Frame(inner, bg=CARD)
                meta_row.pack(fill="x")
                for tag in tags:
                    tk.Label(meta_row, text=f" {tag} ", font=("Consolas", 6),
                             fg=MAUVE, bg=BORDER).pack(side="left", padx=(0, 2))

        if vp == 1:
            # Full: date, source, workaround, notes, action buttons
            meta_row2 = tk.Frame(inner, bg=CARD)
            meta_row2.pack(fill="x")
            tk.Label(meta_row2, text=item.get("date", ""), font=("Segoe UI", 6),
                     fg=BORDER, bg=CARD).pack(side="right")
            tk.Label(meta_row2, text=item.get("source", ""), font=("Segoe UI", 6),
                     fg=BORDER, bg=CARD).pack(side="right", padx=4)

            if item.get("workaround"):
                tk.Label(inner, text=f"Workaround: {item['workaround']}",
                         font=("Segoe UI", 8), fg=TEAL, bg=CARD,
                         wraplength=320, anchor="w", justify="left").pack(fill="x")

            if item.get("notes"):
                tk.Label(inner, text=item["notes"], font=("Segoe UI", 8),
                         fg=DIM, bg=CARD, wraplength=320, anchor="w", justify="left").pack(fill="x")

            btn_row = tk.Frame(inner, bg=CARD)
            btn_row.pack(fill="x", pady=(2, 0))

            for txt, cmd, col in [
                ("severity", lambda i=item: self._cycle_severity(i), sev_col),
                ("+ tag", lambda i=item: self._add_tag(i), MAUVE),
                ("workaround", lambda i=item: self._set_workaround(i), TEAL),
                ("note", lambda i=item: self._set_note(i), DIM),
                ("delete", lambda i=item: self._delete_item(i), RED),
            ]:
                b = tk.Label(btn_row, text=txt, font=("Segoe UI", 6),
                             fg=col, bg=CARD, cursor="hand2", padx=3)
                b.pack(side="left")
                b.bind("<Button-1>", lambda e, c=cmd: c())

    # === ACTIONS ===

    def _toggle_fixed(self, item):
        item["fixed"] = not item.get("fixed", False)
        if item["fixed"]:
            item["fixed_date"] = datetime.now().strftime("%Y-%m-%d")
        save_data(self.data)
        self._render_items()

    def _cycle_severity(self, item):
        cycle = ["low", "medium", "high", "critical"]
        cur = item.get("severity", "medium")
        idx = (cycle.index(cur) + 1) % len(cycle) if cur in cycle else 0
        item["severity"] = cycle[idx]
        save_data(self.data)
        self._render_items()

    def _add_tag(self, item):
        win = tk.Toplevel(self.root)
        win.title("Add tag")
        win.configure(bg=BG)
        win.geometry("220x70")
        win.attributes("-topmost", True)

        var = tk.StringVar()
        e = tk.Entry(win, textvariable=var, bg=CARD, fg=TEXT, insertbackground=TEXT,
                     font=("Segoe UI", 10), relief="flat")
        e.pack(fill="x", padx=10, pady=10, ipady=3)
        e.focus_set()

        def submit(event=None):
            tag = var.get().strip().lower()
            if tag:
                item.setdefault("tags", []).append(tag)
                save_data(self.data)
            win.destroy()
            self._render_items()

        e.bind("<Return>", submit)

    def _set_workaround(self, item):
        win = tk.Toplevel(self.root)
        win.title("Workaround")
        win.configure(bg=BG)
        win.geometry("300x80")
        win.attributes("-topmost", True)

        var = tk.StringVar(value=item.get("workaround", ""))
        e = tk.Entry(win, textvariable=var, bg=CARD, fg=TEXT, insertbackground=TEXT,
                     font=("Segoe UI", 10), relief="flat")
        e.pack(fill="x", padx=10, pady=10, ipady=3)
        e.focus_set()

        def submit(event=None):
            item["workaround"] = var.get().strip()
            save_data(self.data)
            win.destroy()
            self._render_items()

        e.bind("<Return>", submit)

    def _set_note(self, item):
        win = tk.Toplevel(self.root)
        win.title("Note")
        win.configure(bg=BG)
        win.geometry("300x80")
        win.attributes("-topmost", True)

        var = tk.StringVar(value=item.get("notes", ""))
        e = tk.Entry(win, textvariable=var, bg=CARD, fg=TEXT, insertbackground=TEXT,
                     font=("Segoe UI", 10), relief="flat")
        e.pack(fill="x", padx=10, pady=10, ipady=3)
        e.focus_set()

        def submit(event=None):
            item["notes"] = var.get().strip()
            save_data(self.data)
            win.destroy()
            self._render_items()

        e.bind("<Return>", submit)

    def _delete_item(self, item):
        if item in self.data["items"]:
            self.data["items"].remove(item)
            save_data(self.data)
            self._render_items()

    def _export(self):
        write_markdown(self.data)
        self.stats_lbl.config(text=f"Exported to {DB_PATH}")
        self.root.after(3000, lambda: self._render_items())

    def _quit(self, btn=None):
        self._alive = False
        save_data(self.data)
        if self.tray_icon:
            try: self.tray_icon.stop()
            except: pass
        try: self.root.destroy()
        except: pass
        os._exit(0)


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("annoyances.py")
    Annoyances().run()
