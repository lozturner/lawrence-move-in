"""
Lawrence: Move In — Capture v2.0.0
Session-based screenshot brain dump tool.

- Left-click tray icon = take screenshot instantly (no popup)
- Screenshots collected into a session automatically
- Right-click: Capture Now, End Session, Start New Session, Browse, Clear Clipboard
- End Session: compiles all captures into a folder with:
    - compiled.md (all notes + AI summaries in order)
    - compiled.json (structured data ready for any AI)
    - AI call on the full session → summary popup appears automatically
"""
__version__ = "2.0.0"

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
SESSIONS_DIR = SCRIPT_DIR / "capture_sessions"
API_CFG      = SCRIPT_DIR / "kidlin_config.json"
PYTHONW      = Path(sys.executable).with_name("pythonw.exe")

# ── Palette ──────────────────────────────────────────────────────────────────
BG = "#0a0a14"; BG2 = "#12122a"; CARD = "#1a1a3a"; CARD_HI = "#252545"
TEXT = "#cdd6f4"; DIM = "#5a5a80"; LAV = "#b4befe"
GRN = "#a6e3a1"; PCH = "#fab387"; MAU = "#cba6f7"
RED = "#f38ba8"; TEAL = "#94e2d5"; YEL = "#f9e2af"; BLUE = "#89b4fa"

def load_api():
    try:
        d = json.loads(API_CFG.read_text())
        return d.get("api_key",""), d.get("model","claude-sonnet-4-20250514")
    except: return "", "claude-sonnet-4-20250514"

def take_screenshot():
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[0])
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    if img.width > 1280:
        r = 1280 / img.width
        img = img.resize((1280, int(img.height * r)), Image.LANCZOS)
    return img

def img_to_b64(img, quality=65):
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

# ── Session ──────────────────────────────────────────────────────────────────
class CaptureSession:
    def __init__(self):
        self.uid     = uuid4().hex[:6].upper()
        self.started = datetime.now()
        self.ts      = self.started.strftime("%Y%m%d_%H%M%S")
        self.dir     = SESSIONS_DIR / f"{self.ts}_{self.uid}"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "screenshots").mkdir(exist_ok=True)
        self.captures = []  # [{idx, timestamp, screenshot, notes, ai_summary}]

    def add_capture(self, img, notes=""):
        idx = len(self.captures) + 1
        fname = f"{idx:03d}.jpg"
        fpath = self.dir / "screenshots" / fname
        img.save(fpath, format="JPEG", quality=80)

        rec = {
            "idx": idx,
            "uid": uuid4().hex[:8].upper(),
            "timestamp": datetime.now().isoformat(),
            "screenshot": fname,
            "notes": notes,
            "ai_summary": "",
        }
        self.captures.append(rec)
        self._save_index()
        return rec

    def update_notes(self, idx, notes):
        for c in self.captures:
            if c["idx"] == idx:
                c["notes"] = notes
                break
        self._save_index()

    def _save_index(self):
        data = {
            "session_uid": self.uid,
            "started": self.started.isoformat(),
            "capture_count": len(self.captures),
            "captures": self.captures,
        }
        (self.dir / "session.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def compile(self):
        """Compile all captures into final deliverables."""
        # compiled.json — structured, AI-ready
        compiled_json = {
            "session_uid": self.uid,
            "started": self.started.isoformat(),
            "ended": datetime.now().isoformat(),
            "capture_count": len(self.captures),
            "captures": [],
        }
        for c in self.captures:
            compiled_json["captures"].append({
                "index": c["idx"],
                "timestamp": c["timestamp"],
                "notes": c["notes"],
                "ai_summary": c.get("ai_summary", ""),
                "screenshot_file": c["screenshot"],
            })

        (self.dir / "compiled.json").write_text(
            json.dumps(compiled_json, indent=2, ensure_ascii=False), encoding="utf-8")

        # compiled.md — human-readable
        md = [
            f"# Capture Session {self.uid}\n\n",
            f"**Started:** {self.started:%Y-%m-%d %H:%M}\n",
            f"**Ended:** {datetime.now():%Y-%m-%d %H:%M}\n",
            f"**Captures:** {len(self.captures)}\n\n---\n\n",
        ]
        for c in self.captures:
            md.append(f"## Capture {c['idx']} — {c['timestamp'][:19]}\n\n")
            md.append(f"![screenshot](screenshots/{c['screenshot']})\n\n")
            if c["notes"]:
                md.append(f"**Notes:** {c['notes']}\n\n")
            if c.get("ai_summary"):
                md.append(f"**AI:** {c['ai_summary']}\n\n")
            md.append("---\n\n")

        (self.dir / "compiled.md").write_text("".join(md), encoding="utf-8")

        # AI prompt — ready to paste into any LLM
        prompt = (
            f"Here is a capture session with {len(self.captures)} screenshots and notes.\n"
            f"Session started: {self.started:%Y-%m-%d %H:%M}\n\n"
            f"Please analyze the full session and tell me:\n"
            f"1. What was I working on across these captures?\n"
            f"2. What was the progression/flow of my work?\n"
            f"3. Any observations about patterns or focus?\n"
            f"4. Suggested next steps\n\n"
            f"--- SESSION DATA ---\n\n"
        )
        for c in self.captures:
            prompt += f"[Capture {c['idx']}] {c['timestamp'][:19]}\n"
            if c["notes"]:
                prompt += f"  Notes: {c['notes']}\n"
            if c.get("ai_summary"):
                prompt += f"  AI saw: {c['ai_summary']}\n"
            prompt += "\n"

        (self.dir / "ai_prompt.txt").write_text(prompt, encoding="utf-8")

        return compiled_json, prompt


# ── App ───────────────────────────────────────────────────────────────────────
class CaptureApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self._session = None
        self._start_tray()
        self.root.mainloop()

    def _ensure_session(self):
        if not self._session:
            self._session = CaptureSession()

    # ── Quick capture (single tray click) ─────────────────────────────────
    def _quick_capture(self):
        """Single click: screenshot instantly, add to session, flash notification."""
        self._ensure_session()
        img = take_screenshot()
        rec = self._session.add_capture(img)

        # Quick notification
        n = len(self._session.captures)
        self._flash_notify(
            f"📸 #{n} captured",
            f"Session {self._session.uid} — {n} screenshot{'s' if n>1 else ''}")

    # ── Capture with notes popup ──────────────────────────────────────────
    def _capture_with_notes(self):
        self._ensure_session()
        img = take_screenshot()
        rec = self._session.add_capture(img)
        self._show_notes_popup(rec, img)

    def _show_notes_popup(self, rec, img):
        win = tk.Toplevel(self.root)
        win.title(f"Capture #{rec['idx']}")
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.96)
        win.configure(bg=BG)

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        w, h = min(580, sw-60), min(420, sh-60)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # Header
        hdr = tk.Frame(win, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  📸 #{rec['idx']}  —  Session {self._session.uid}",
                 font=("Consolas",10,"bold"), fg=PCH, bg=BG2).pack(
                     side="left", padx=8, ipady=6)
        n = len(self._session.captures)
        tk.Label(hdr, text=f"{n} in session",
                 font=("Segoe UI",8), fg=DIM, bg=BG2).pack(side="right", padx=10)

        # Screenshot preview
        prev = img.copy()
        pw = min(540, w - 30)
        ratio = pw / prev.width
        prev = prev.resize((pw, int(prev.height * ratio)), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(prev)
        tk.Label(win, image=self._photo, bg="#000").pack(padx=8, pady=(6,4))

        # Notes
        nf = tk.Frame(win, bg=CARD, padx=4, pady=4)
        nf.pack(fill="x", padx=8)
        txt = tk.Text(nf, bg="#12122a", fg=TEXT, insertbackground=LAV,
                      font=("Segoe UI",10), wrap="word", height=3, relief="flat")
        txt.pack(fill="x")
        txt.focus_set()

        # Buttons
        bf = tk.Frame(win, bg=BG)
        bf.pack(fill="x", padx=8, pady=6)

        def _save():
            notes = txt.get("1.0","end").strip()
            self._session.update_notes(rec["idx"], notes)
            win.destroy()

        tk.Label(bf, text="  Save note  ", bg=GRN, fg=BG,
                 font=("Segoe UI",9,"bold"), padx=10, pady=4,
                 cursor="hand2").pack(side="left")
        bf.winfo_children()[-1].bind("<Button-1>", lambda _: _save())

        tk.Label(bf, text="  Skip  ", bg=CARD, fg=DIM,
                 font=("Segoe UI",9), padx=10, pady=4,
                 cursor="hand2").pack(side="left", padx=(6,0))
        bf.winfo_children()[-1].bind("<Button-1>", lambda _: win.destroy())

        txt.bind("<Control-Return>", lambda _: _save())

    # ── End session ───────────────────────────────────────────────────────
    def _end_session(self):
        if not self._session or not self._session.captures:
            self._flash_notify("No session", "Nothing to compile")
            return

        session = self._session
        self._session = None  # clear so next capture starts fresh

        # Compile
        compiled_json, prompt = session.compile()

        # Copy prompt to clipboard
        copy_clip(prompt)

        # Try AI summary of the full session
        api_key, model = load_api()
        if api_key:
            self._ai_session_summary(session, compiled_json, prompt, api_key, model)
        else:
            self._show_session_end_popup(session, compiled_json, prompt, None)

    def _ai_session_summary(self, session, compiled_json, prompt, api_key, model):
        def _run():
            try:
                import anthropic
                cl = anthropic.Anthropic(api_key=api_key)

                # Build message with all screenshots + notes
                content = []
                for c in session.captures[:10]:  # max 10 images for API
                    img_path = session.dir / "screenshots" / c["screenshot"]
                    if img_path.exists():
                        img = Image.open(img_path)
                        b64 = img_to_b64(img)
                        content.append({
                            "type": "image",
                            "source": {"type":"base64","media_type":"image/jpeg","data":b64}
                        })
                        if c["notes"]:
                            content.append({"type":"text","text":f"[#{c['idx']}] Notes: {c['notes']}"})

                content.append({"type":"text","text":
                    f"This is a capture session of {len(session.captures)} screenshots. "
                    f"Summarize: what was the user doing across these captures? "
                    f"What was the progression? Any patterns? Suggested next steps? "
                    f"Keep it to 4-6 sentences."
                })

                r = cl.messages.create(model=model, max_tokens=400,
                                       messages=[{"role":"user","content":content}])
                summary = r.content[0].text.strip()
            except Exception as e:
                summary = f"AI error: {e}"

            self.root.after(0, lambda:
                self._show_session_end_popup(session, compiled_json, prompt, summary))

        threading.Thread(target=_run, daemon=True).start()
        self._flash_notify("Compiling session…", f"{len(session.captures)} captures → AI processing")

    def _show_session_end_popup(self, session, compiled_json, prompt, ai_summary):
        win = tk.Toplevel(self.root)
        win.title(f"Session {session.uid} — Complete")
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.96)
        win.configure(bg=BG)

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        w, h = min(650, sw-60), min(520, sh-60)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # Header
        hdr = tk.Frame(win, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  Session {session.uid} complete",
                 font=("Consolas",12,"bold"), fg=GRN, bg=BG2).pack(
                     side="left", padx=8, ipady=8)
        xb = tk.Label(hdr, text=" ✕ ", font=("Consolas",11),
                       fg=DIM, bg=BG2, cursor="hand2")
        xb.pack(side="right", padx=6)
        xb.bind("<Button-1>", lambda _: win.destroy())

        # Stats
        sf = tk.Frame(win, bg=CARD)
        sf.pack(fill="x", padx=12, pady=8)
        for label, val, col in [
            ("Captures", str(len(session.captures)), PCH),
            ("Duration", f"{(datetime.now()-session.started).seconds//60}min", BLUE),
            ("Folder", session.dir.name, DIM),
        ]:
            f = tk.Frame(sf, bg=CARD, padx=12, pady=6)
            f.pack(side="left")
            tk.Label(f, text=val, font=("Consolas",14,"bold"),
                     fg=col, bg=CARD).pack()
            tk.Label(f, text=label, font=("Segoe UI",7),
                     fg=DIM, bg=CARD).pack()

        # AI Summary
        if ai_summary:
            tk.Label(win, text="AI Session Summary",
                     font=("Segoe UI",9,"bold"), fg=MAU, bg=BG,
                     anchor="w").pack(fill="x", padx=14, pady=(8,2))
            tk.Label(win, text=ai_summary, font=("Segoe UI",10),
                     fg=TEXT, bg=CARD, wraplength=600, justify="left",
                     anchor="nw", padx=12, pady=8).pack(fill="x", padx=12)

        # Files created
        tk.Label(win, text="Files created",
                 font=("Segoe UI",9,"bold"), fg=TEAL, bg=BG,
                 anchor="w").pack(fill="x", padx=14, pady=(10,2))
        for fname in ["compiled.md", "compiled.json", "ai_prompt.txt", "session.json"]:
            fp = session.dir / fname
            if fp.exists():
                tk.Label(win, text=f"  {fname}  ({fp.stat().st_size//1024}KB)",
                         font=("Consolas",8), fg=DIM, bg=BG,
                         anchor="w").pack(fill="x", padx=14)

        # Action buttons
        tk.Label(win, text="AI prompt copied to clipboard — paste into any LLM",
                 font=("Segoe UI",8), fg=YEL, bg=BG).pack(pady=(8,2))

        bf = tk.Frame(win, bg=BG)
        bf.pack(fill="x", padx=12, pady=(4,12))

        for txt, fn in [
            ("📋 Copy prompt again",
             lambda: copy_clip(prompt)),
            ("📋 Copy JSON",
             lambda: copy_clip(json.dumps(compiled_json, indent=2))),
            ("📁 Open folder",
             lambda: os.startfile(str(session.dir))),
        ]:
            b = tk.Label(bf, text=f"  {txt}  ", font=("Segoe UI",8),
                         fg=TEXT, bg=CARD, padx=8, pady=4, cursor="hand2")
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, f=fn: f())
            b.bind("<Enter>", lambda e, w=b: w.config(bg=CARD_HI))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=CARD))

    # ── Start new session ─────────────────────────────────────────────────
    def _start_new_session(self):
        if self._session and self._session.captures:
            # End current first
            self._end_session()
        self._session = CaptureSession()
        self._flash_notify("New session", f"Session {self._session.uid} started")

    # ── Flash notification ────────────────────────────────────────────────
    def _flash_notify(self, title, body):
        n = tk.Toplevel(self.root)
        n.overrideredirect(True)
        n.attributes("-topmost", True)
        n.attributes("-alpha", 0.95)
        n.configure(bg=BG2)

        sw = n.winfo_screenwidth()
        nw = 340
        n.geometry(f"{nw}x70+{sw-nw-20}+{40}")

        tk.Label(n, text=f"  {title}", font=("Segoe UI",9,"bold"),
                 fg=PCH, bg=BG2, anchor="w").pack(fill="x", padx=6, pady=(8,0))
        tk.Label(n, text=f"  {body}", font=("Segoe UI",8),
                 fg=DIM, bg=BG2, anchor="w").pack(fill="x", padx=6)

        n.bind("<Button-1>", lambda _: n.destroy())
        n.after(3000, lambda: n.destroy() if n.winfo_exists() else None)

    # ── Browse ────────────────────────────────────────────────────────────
    def _browse(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        sessions = sorted(
            [d for d in SESSIONS_DIR.iterdir() if (d/"session.json").exists()],
            reverse=True)

        dlg = tk.Toplevel(self.root)
        dlg.title("Capture Sessions")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=BG)
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"420x400+{(sw-420)//2}+{(sh-400)//2}")

        tk.Label(dlg, text="  📸 Capture Sessions", bg=BG2, fg=PCH,
                 font=("Consolas",11,"bold"), anchor="w").pack(fill="x", ipady=8)

        active = self._session
        if active and active.captures:
            af = tk.Frame(dlg, bg="#1a2a1a")
            af.pack(fill="x", padx=8, pady=4)
            tk.Label(af, text=f"  Active: {active.uid} — {len(active.captures)} captures",
                     font=("Segoe UI",9,"bold"), fg=GRN, bg="#1a2a1a",
                     anchor="w").pack(fill="x", padx=8, ipady=6)

        cf = tk.Frame(dlg, bg=BG)
        cf.pack(fill="both", expand=True, padx=8, pady=4)

        if not sessions:
            tk.Label(cf, text="No sessions yet.\nLeft-click the tray icon to start capturing.",
                     font=("Segoe UI",10), fg=DIM, bg=BG).pack(expand=True)
        else:
            for s in sessions[:15]:
                try:
                    d = json.loads((s/"session.json").read_text(encoding="utf-8"))
                    uid = d.get("session_uid","?")
                    ts  = d.get("started","")[:16]
                    cnt = d.get("capture_count",0)
                    compiled = (s/"compiled.md").exists()
                    status = "compiled" if compiled else "raw"
                    label = f"{uid}  {ts}  {cnt} caps  [{status}]"
                except: label = s.name

                row = tk.Label(cf, text=label, font=("Consolas",8),
                               fg=TEXT, bg=CARD, anchor="w", padx=10, pady=5,
                               cursor="hand2")
                row.pack(fill="x", pady=1)

                def _open(e, sd=s):
                    os.startfile(str(sd))

                row.bind("<Button-1>", _open)
                row.bind("<Enter>", lambda e, w=row: w.config(bg=CARD_HI))
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

        def _session_label(_):
            if self._session and self._session.captures:
                return f"Session {self._session.uid}: {len(self._session.captures)} captures"
            return "No active session"

        menu = pystray.Menu(
            pystray.MenuItem(_session_label, lambda i,it: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📸 Capture Now (with notes)",
                lambda icon, item: self.root.after(0, self._capture_with_notes)),
            pystray.MenuItem("📸 End Session & Compile",
                lambda icon, item: self.root.after(0, self._end_session)),
            pystray.MenuItem("📸 Start New Session",
                lambda icon, item: self.root.after(0, self._start_new_session)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Browse Sessions",
                lambda icon, item: self.root.after(0, self._browse)),
            pystray.MenuItem("Clear Clipboard",
                lambda icon, item: copy_clip("")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",
                lambda icon, item: self._quit(icon)),
        )
        self._tray = pystray.Icon("capture", img, "Capture", menu)
        # Left-click = instant screenshot, no popup
        self._tray.default_action = lambda icon, item: self.root.after(0, self._quick_capture)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _quit(self, icon=None):
        # Auto-end session on quit if there are captures
        if self._session and self._session.captures:
            self._session.compile()
        if icon: icon.stop()
        try: self.root.destroy()
        except: pass


if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("capture.py")
    CaptureApp()
