"""
Lawrence: Move In — Capture v1.0.0
Morning brain-dump tool. One click from the system tray:
  1. Takes a screenshot
  2. Pops up a chatbot form
  3. You talk/type into it
  4. Both records (screenshot + notes) get bundled
  5. Unique code + URL generated
  6. Copies to clipboard
  7. Notification pops with what it did and what you can do next

System tray controls:
  - Left-click tray icon: capture now
  - Right-click: settings, browse captures, clear clipboard
"""
__version__ = "1.0.0"

import base64, io, json, os, subprocess, sys, threading, time, tkinter as tk
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import mss
import pystray
import win32clipboard
from PIL import Image, ImageDraw, ImageFont, ImageTk

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
CAPTURES_DIR = SCRIPT_DIR / "captures"
API_CFG      = SCRIPT_DIR / "kidlin_config.json"
PYTHONW      = Path(sys.executable).with_name("pythonw.exe")

# ── Palette ──────────────────────────────────────────────────────────────────
BG = "#0a0a14"; BG2 = "#12122a"; CARD = "#1a1a3a"
TEXT = "#cdd6f4"; DIM = "#5a5a80"; LAV = "#b4befe"
GRN = "#a6e3a1"; PCH = "#fab387"; MAU = "#cba6f7"
RED = "#f38ba8"; TEAL = "#94e2d5"; YEL = "#f9e2af"
BLUE = "#89b4fa"

def load_api():
    try:
        d = json.loads(API_CFG.read_text())
        return d.get("api_key",""), d.get("model","claude-sonnet-4-20250514")
    except: return "", "claude-sonnet-4-20250514"

def take_screenshot():
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[0])
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    max_w = 1280
    if img.width > max_w:
        r = max_w / img.width
        img = img.resize((max_w, int(img.height * r)), Image.LANCZOS)
    return img

def img_to_b64(img, quality=70):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()

def copy_clip(text):
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text)
        win32clipboard.CloseClipboard()
    except:
        try: win32clipboard.CloseClipboard()
        except: pass

# ── Capture Record ───────────────────────────────────────────────────────────
class CaptureRecord:
    def __init__(self):
        self.uid       = uuid4().hex[:8].upper()
        self.timestamp = datetime.now()
        self.ts_str    = self.timestamp.strftime("%Y%m%d_%H%M%S")
        self.dir       = CAPTURES_DIR / f"{self.ts_str}_{self.uid}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_path = None
        self.notes     = ""
        self.ai_summary= ""

    def save_screenshot(self, img):
        self.screenshot_path = self.dir / "screenshot.jpg"
        img.save(self.screenshot_path, format="JPEG", quality=80)

    def save(self):
        data = {
            "uid": self.uid,
            "timestamp": self.timestamp.isoformat(),
            "notes": self.notes,
            "ai_summary": self.ai_summary,
            "screenshot": str(self.screenshot_path) if self.screenshot_path else None,
        }
        (self.dir / "capture.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # Also save a readable markdown
        md = [
            f"# Capture {self.uid} — {self.timestamp:%Y-%m-%d %H:%M}\n\n",
            f"**Code:** `{self.uid}`\n\n",
        ]
        if self.notes:
            md.append(f"## Notes\n\n{self.notes}\n\n")
        if self.ai_summary:
            md.append(f"## AI Summary\n\n{self.ai_summary}\n\n")
        if self.screenshot_path:
            md.append(f"## Screenshot\n\n![screenshot](screenshot.jpg)\n")

        (self.dir / "capture.md").write_text("".join(md), encoding="utf-8")

    def clipboard_text(self):
        lines = [f"[Capture {self.uid}] {self.timestamp:%Y-%m-%d %H:%M}"]
        if self.notes:
            lines.append(self.notes[:200])
        if self.ai_summary:
            lines.append(f"AI: {self.ai_summary[:200]}")
        lines.append(f"File: {self.dir}")
        return "\n".join(lines)


# ── Capture UI ────────────────────────────────────────────────────────────────
class CaptureApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self._win = None
        self._start_tray()
        self.root.mainloop()

    def _do_capture(self):
        """Main capture flow: screenshot → popup → bundle → notify."""
        rec = CaptureRecord()

        # 1. Screenshot
        img = take_screenshot()
        rec.save_screenshot(img)

        # 2. Show popup
        self._show_popup(rec, img)

    def _show_popup(self, rec, screenshot_img):
        if self._win:
            try: self._win.destroy()
            except: pass

        win = tk.Toplevel(self.root)
        win.title(f"Capture {rec.uid}")
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.96)
        win.configure(bg=BG)
        self._win = win

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        w, h = min(640, sw-60), min(550, sh-60)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # Header
        hdr = tk.Frame(win, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  📸 Capture {rec.uid}",
                 font=("Consolas",11,"bold"), fg=PCH, bg=BG2).pack(
                     side="left", padx=8, ipady=8)
        tk.Label(hdr, text=rec.timestamp.strftime("%H:%M:%S"),
                 font=("Consolas",10), fg=DIM, bg=BG2).pack(
                     side="right", padx=10)

        xb = tk.Label(hdr, text=" ✕ ", font=("Consolas",11),
                       fg=DIM, bg=BG2, cursor="hand2")
        xb.pack(side="right", padx=4)
        xb.bind("<Button-1>", lambda _: self._cancel(win))

        # Screenshot preview
        prev_img = screenshot_img.copy()
        prev_w = min(600, w - 40)
        ratio = prev_w / prev_img.width
        prev_img = prev_img.resize((prev_w, int(prev_img.height * ratio)), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(prev_img)

        img_lbl = tk.Label(win, image=self._photo, bg="#000")
        img_lbl.pack(padx=10, pady=(8,4))

        tk.Label(win, text="Screenshot captured. What's on your mind?",
                 font=("Segoe UI",9), fg=DIM, bg=BG).pack(pady=(2,4))

        # Notes input
        nf = tk.Frame(win, bg=CARD, padx=6, pady=6)
        nf.pack(fill="x", padx=10)
        self._txt = tk.Text(nf, bg="#12122a", fg=TEXT, insertbackground=LAV,
                            font=("Segoe UI",11), wrap="word", height=4,
                            relief="flat")
        self._txt.pack(fill="x")
        self._txt.focus_set()

        # Status
        self._cap_stat = tk.Label(win, text="", font=("Segoe UI",8),
                                  fg=DIM, bg=BG)
        self._cap_stat.pack(pady=2)

        # Buttons
        bf = tk.Frame(win, bg=BG)
        bf.pack(fill="x", padx=10, pady=(4,10))

        for txt, col, cmd in [
            ("📸 Save & Process", GRN,
             lambda: self._save_and_process(rec, screenshot_img, win)),
            ("📸 Save (no AI)", BLUE,
             lambda: self._save_only(rec, win)),
            ("Cancel", DIM,
             lambda: self._cancel(win)),
        ]:
            b = tk.Label(bf, text=f"  {txt}  ", font=("Segoe UI",9,"bold"),
                         fg=BG if col != DIM else TEXT,
                         bg=col if col != DIM else CARD,
                         padx=12, pady=6, cursor="hand2")
            b.pack(side="left", padx=(0,6))
            b.bind("<Button-1>", lambda e, fn=cmd: fn())

        self._txt.bind("<Control-Return>",
            lambda _: self._save_and_process(rec, screenshot_img, win))

    def _save_only(self, rec, win):
        rec.notes = self._txt.get("1.0","end").strip()
        rec.save()
        clip = rec.clipboard_text()
        copy_clip(clip)
        win.destroy()
        self._notify(rec, "Saved (no AI)")

    def _save_and_process(self, rec, screenshot_img, win):
        rec.notes = self._txt.get("1.0","end").strip()
        self._cap_stat.config(text="Processing with AI…", fg=PCH)

        api_key, model = load_api()
        if not api_key:
            rec.save()
            clip = rec.clipboard_text()
            copy_clip(clip)
            win.destroy()
            self._notify(rec, "Saved (no API key for AI)")
            return

        def _run():
            try:
                import anthropic
                cl = anthropic.Anthropic(api_key=api_key)

                b64 = img_to_b64(screenshot_img)
                content = [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg", "data": b64}},
                ]
                prompt = (
                    "The user just captured their screen and wrote these notes:\n\n"
                    f'"{rec.notes}"\n\n' if rec.notes else
                    "The user just captured their screen.\n\n"
                )
                prompt += (
                    "In 2-3 sentences: what are they looking at, "
                    "what did they want to remember, and what should they do next? "
                    "Be specific — read the screen content."
                )
                content.append({"type": "text", "text": prompt})

                r = cl.messages.create(
                    model=model, max_tokens=200,
                    messages=[{"role":"user","content": content}])
                rec.ai_summary = r.content[0].text.strip()
            except Exception as e:
                rec.ai_summary = f"AI error: {e}"

            rec.save()
            clip = rec.clipboard_text()
            copy_clip(clip)
            self.root.after(0, lambda: (win.destroy(), self._notify(rec, "Processed")))

        threading.Thread(target=_run, daemon=True).start()

    def _cancel(self, win):
        win.destroy()

    # ── Notification ──────────────────────────────────────────────────────
    def _notify(self, rec, status):
        n = tk.Toplevel(self.root)
        n.overrideredirect(True)
        n.attributes("-topmost", True)
        n.attributes("-alpha", 0.95)
        n.configure(bg=BG2)

        sw = n.winfo_screenwidth()
        nw = 380
        n.geometry(f"{nw}x160+{sw-nw-20}+{40}")

        tk.Label(n, text=f"📸 Capture {rec.uid} — {status}",
                 font=("Segoe UI",10,"bold"), fg=PCH, bg=BG2,
                 anchor="w").pack(fill="x", padx=12, pady=(10,4))

        lines = []
        if rec.notes:
            lines.append(f"Notes: {rec.notes[:60]}{'…' if len(rec.notes)>60 else ''}")
        if rec.ai_summary:
            lines.append(f"AI: {rec.ai_summary[:60]}{'…' if len(rec.ai_summary)>60 else ''}")
        lines.append(f"📋 Copied to clipboard")
        lines.append(f"📁 Saved to captures/{rec.dir.name}")

        for line in lines:
            tk.Label(n, text=line, font=("Segoe UI",8),
                     fg=TEXT, bg=BG2, anchor="w").pack(fill="x", padx=12)

        tk.Label(n, text="click to dismiss",
                 font=("Segoe UI",7), fg=DIM, bg=BG2).pack(pady=(6,0))
        n.bind("<Button-1>", lambda _: n.destroy())
        n.after(8000, lambda: n.destroy() if n.winfo_exists() else None)

    # ── Browse captures ───────────────────────────────────────────────────
    def _browse(self):
        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        caps = sorted(
            [d for d in CAPTURES_DIR.iterdir() if (d/"capture.json").exists()],
            reverse=True)

        dlg = tk.Toplevel(self.root)
        dlg.title("Captures")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=BG)
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"400x450+{(sw-400)//2}+{(sh-450)//2}")

        tk.Label(dlg, text="  📸 Captures", bg=BG2, fg=PCH,
                 font=("Consolas",11,"bold"), anchor="w").pack(fill="x", ipady=8)

        cf = tk.Frame(dlg, bg=BG)
        cf.pack(fill="both", expand=True, padx=8, pady=4)

        if not caps:
            tk.Label(cf, text="No captures yet.\nClick the tray icon to start.",
                     font=("Segoe UI",10), fg=DIM, bg=BG).pack(expand=True)
        else:
            for c in caps[:20]:
                try:
                    d = json.loads((c/"capture.json").read_text(encoding="utf-8"))
                    uid  = d.get("uid","?")
                    ts   = d.get("timestamp","")[:16]
                    note = (d.get("notes","") or "")[:40]
                    label = f"{uid}  {ts}  {note}"
                except:
                    label = c.name

                row = tk.Label(cf, text=label, font=("Consolas",9),
                               fg=TEXT, bg=CARD, anchor="w", padx=10, pady=5,
                               cursor="hand2")
                row.pack(fill="x", pady=1)

                def _click(e, cap_dir=c):
                    # Copy capture to clipboard
                    try:
                        d = json.loads((cap_dir/"capture.json").read_text(encoding="utf-8"))
                        clip = f"[Capture {d['uid']}] {d['timestamp'][:16]}\n"
                        if d.get("notes"): clip += f"{d['notes'][:200]}\n"
                        if d.get("ai_summary"): clip += f"AI: {d['ai_summary'][:200]}\n"
                        clip += f"File: {cap_dir}"
                        copy_clip(clip)
                    except: pass

                row.bind("<Button-1>", _click)
                row.bind("<Enter>", lambda e, w=row: w.config(bg="#252545"))
                row.bind("<Leave>", lambda e, w=row: w.config(bg=CARD))

        cb = tk.Label(dlg, text="Close", bg=BG2, fg=DIM,
                      font=("Segoe UI",8), cursor="hand2", pady=4)
        cb.pack(fill="x")
        cb.bind("<Button-1>", lambda _: dlg.destroy())

    # ── Tray ──────────────────────────────────────────────────────────────
    def _start_tray(self):
        img = Image.new("RGBA",(64,64),(0,0,0,0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([4,4,59,59], radius=12, fill=(250,179,135))
        try: fnt = ImageFont.truetype("consola.ttf",20)
        except: fnt = ImageFont.load_default()
        bb = d.textbbox((0,0),"CP",font=fnt)
        d.text(((64-(bb[2]-bb[0]))//2,(64-(bb[3]-bb[1]))//2),
               "CP", fill="#0a0a14", font=fnt)

        menu = pystray.Menu(
            pystray.MenuItem("📸 Capture Now",
                lambda icon, item: self.root.after(0, self._do_capture)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Browse Captures",
                lambda icon, item: self.root.after(0, self._browse)),
            pystray.MenuItem("Clear Clipboard",
                lambda icon, item: copy_clip("")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",
                lambda icon, item: self._quit(icon)),
        )
        self._tray = pystray.Icon("capture", img, "Capture", menu)
        # Left-click tray icon = capture
        self._tray.default_action = lambda icon, item: self.root.after(0, self._do_capture)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _quit(self, icon=None):
        if icon: icon.stop()
        try: self.root.destroy()
        except: pass


if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("capture.py")
    CaptureApp()
