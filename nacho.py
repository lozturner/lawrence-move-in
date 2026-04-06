"""
Lawrence: Move In — NACHO v2.0.0
Loz's voice AI. Fast, lightweight, hyperlinked conversation.
Every sentence is a clickable link — hover underlines, click opens actions.
Delete individual messages. Export the whole chat.
"""
__version__ = "2.0.0"

import json, os, queue, re, subprocess, sys, threading, time, tkinter as tk
from datetime import datetime
from pathlib import Path

import pyttsx3, sounddevice as sd
from PIL import Image, ImageDraw, ImageFont
from vosk import Model, KaldiRecognizer

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
API_CFG    = SCRIPT_DIR / "kidlin_config.json"
LOG_DIR    = SCRIPT_DIR / "nacho_log"
PYTHONW    = Path(sys.executable).with_name("pythonw.exe")
VOSK_SMALL = SCRIPT_DIR / "vosk-model-small-en-us-0.15"
VOSK_LARGE = SCRIPT_DIR / "vosk-model-en-us-0.22-lgraph"

# ── Palette ──────────────────────────────────────────────────────────────────
BG   = "#0a0a14"; BG2  = "#12122a"; CARD = "#1a1a3a"
TEXT = "#cdd6f4"; DIM  = "#5a5a80"; LAV  = "#b4befe"
GRN  = "#a6e3a1"; PCH  = "#fab387"; MAU  = "#cba6f7"
RED  = "#f38ba8"; TEAL = "#94e2d5"; YEL  = "#f9e2af"

GREETING = "Hi Loz. What are you up to?"
SYS_PROMPT = (
    "You are NACHO, Loz's personal AI. Like the crisp. "
    "Casual, warm, British-friendly. 2-3 sentences max. "
    "Loz is a dev with ADHD, father of 4. Be direct, not annoying."
)

# ── Preload API config ───────────────────────────────────────────────────────
def _load_api():
    try:
        d = json.loads(API_CFG.read_text())
        return d.get("api_key", ""), d.get("model", "claude-sonnet-4-20250514")
    except Exception:
        return "", "claude-sonnet-4-20250514"

# ── Preloaded TTS engine (single instance, fast) ─────────────────────────────
_tts_engine = None
_tts_lock   = threading.Lock()

def _init_tts():
    global _tts_engine
    if _tts_engine:
        return
    _tts_engine = pyttsx3.init()
    _tts_engine.setProperty("rate", 175)
    for v in _tts_engine.getProperty("voices"):
        if "zira" in v.name.lower() or "hazel" in v.name.lower():
            _tts_engine.setProperty("voice", v.id)
            break

def speak(text, done_cb=None):
    def _go():
        with _tts_lock:
            try:
                _init_tts()
                _tts_engine.say(text)
                _tts_engine.runAndWait()
            except Exception:
                pass
        if done_cb:
            done_cb()
    threading.Thread(target=_go, daemon=True).start()

# ── Preloaded Vosk model ─────────────────────────────────────────────────────
_vosk_model = None

def _get_vosk():
    global _vosk_model
    if _vosk_model:
        return _vosk_model
    path = VOSK_SMALL if VOSK_SMALL.exists() else VOSK_LARGE
    if not path.exists():
        return None
    _vosk_model = Model(str(path))
    return _vosk_model

# ── Listener ─────────────────────────────────────────────────────────────────
class Mic:
    def __init__(self, on_final, on_partial):
        self._on_final   = on_final
        self._on_partial = on_partial
        self._q       = queue.Queue()
        self._active  = False
        self._stream  = None

    def start(self):
        model = _get_vosk()
        if not model:
            return
        self._rec    = KaldiRecognizer(model, 16000)
        self._active = True
        self._stream = sd.RawInputStream(
            samplerate=16000, blocksize=8000, dtype="int16",
            channels=1, callback=self._cb)
        self._stream.start()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._active = False
        if self._stream:
            try: self._stream.stop(); self._stream.close()
            except: pass
            self._stream = None

    def _cb(self, data, frames, t, status):
        if self._active:
            self._q.put(bytes(data))

    def _loop(self):
        last_partial = time.time()
        while self._active:
            try:
                data = self._q.get(timeout=0.2)
            except queue.Empty:
                # 4s silence after last partial → finalize
                if time.time() - last_partial > 4.0 and last_partial > 0:
                    res = json.loads(self._rec.FinalResult())
                    txt = res.get("text", "").strip()
                    self.stop()
                    self._on_final(txt)
                    return
                continue

            if self._rec.AcceptWaveform(data):
                res = json.loads(self._rec.Result())
                txt = res.get("text", "").strip()
                if txt:
                    self.stop()
                    self._on_final(txt)
                    return
            else:
                p = json.loads(self._rec.PartialResult()).get("partial", "")
                if p:
                    last_partial = time.time()
                    self._on_partial(p)

# ── App ───────────────────────────────────────────────────────────────────────
class NachoApp:
    def __init__(self):
        self._msgs  = []   # [{id, role, text}]
        self._mid   = 0
        self._mic   = None
        self._abar  = None

        self.root = tk.Tk()
        self.root.withdraw()

        # Preload vosk in background
        threading.Thread(target=_get_vosk, daemon=True).start()

        self._build()
        self.root.after(200, self._greet)
        self._start_tray()
        self.root.mainloop()

    def _next_id(self):
        self._mid += 1
        return self._mid

    # ── Build ─────────────────────────────────────────────────────────────
    def _build(self):
        self._ovl = tk.Toplevel(self.root)
        self._ovl.attributes("-topmost", True)
        self._ovl.attributes("-alpha", 0.94)
        self._ovl.configure(bg=BG)

        sw = self._ovl.winfo_screenwidth()
        sh = self._ovl.winfo_screenheight()
        w, h = min(780, sw - 80), min(480, sh - 120)
        self._ovl.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # Header
        hdr = tk.Frame(self._ovl, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  NACHO", font=("Consolas",13,"bold"),
                 fg=MAU, bg=BG2).pack(side="left", padx=8, ipady=8)
        self._stat = tk.Label(hdr, text="", font=("Segoe UI",8),
                              fg=DIM, bg=BG2)
        self._stat.pack(side="left", padx=8)

        # Header buttons
        for txt, col, cmd in [
            (" ✕ ", RED, self._close),
            (" 📤 ", TEAL, self._export),
        ]:
            b = tk.Label(hdr, text=txt, font=("Segoe UI",11),
                         fg=col, bg=BG2, cursor="hand2")
            b.pack(side="right", padx=4)
            b.bind("<Button-1>", lambda e, fn=cmd: fn())

        # Drag
        for w in (hdr,) + tuple(hdr.winfo_children()):
            w.bind("<Button-1>", self._ds)
            w.bind("<B1-Motion>", self._dm)

        # Chat scroll
        c = tk.Frame(self._ovl, bg=BG)
        c.pack(fill="both", expand=True, padx=10, pady=6)
        self._cv = tk.Canvas(c, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(c, orient="vertical", command=self._cv.yview, width=5)
        self._cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._cv.pack(fill="both", expand=True)
        self._cf = tk.Frame(self._cv, bg=BG)
        self._cw = self._cv.create_window((0, 0), window=self._cf, anchor="nw")
        self._cf.bind("<Configure>",
            lambda e: self._cv.config(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>",
            lambda e: self._cv.itemconfig(self._cw, width=e.width))
        self._cv.bind("<Enter>",
            lambda e: self.root.bind_all("<MouseWheel>", self._wh))
        self._cv.bind("<Leave>",
            lambda e: self.root.unbind_all("<MouseWheel>"))

        # Mic button
        mf = tk.Frame(self._ovl, bg=BG)
        mf.pack(fill="x", padx=10, pady=(0, 12))
        self._mb = tk.Label(mf, text="🎙️  Tap to speak",
                            font=("Segoe UI", 11, "bold"),
                            fg=GRN, bg=CARD, padx=20, pady=8, cursor="hand2")
        self._mb.pack()
        self._mb.bind("<Button-1>", lambda _: self._listen())
        self._mb.bind("<Enter>", lambda _: self._mb.config(bg="#252545"))
        self._mb.bind("<Leave>", lambda _: self._mb.config(bg=CARD))

    def _wh(self, e):
        try: self._cv.yview_scroll(-(e.delta // 120), "units")
        except: pass

    def _ds(self, e):
        self._dx, self._dy = e.x, e.y

    def _dm(self, e):
        self._ovl.geometry(
            f"+{self._ovl.winfo_x()+e.x-self._dx}+"
            f"{self._ovl.winfo_y()+e.y-self._dy}")

    # ── Messages ──────────────────────────────────────────────────────────
    def _add(self, role, text):
        mid = self._next_id()
        self._msgs.append({"id": mid, "role": role, "text": text})
        self._draw_msg(mid, role, text)
        self.root.update_idletasks()
        self._cv.yview_moveto(1.0)

    def _draw_msg(self, mid, role, text):
        is_nacho = role == "nacho"
        color    = MAU if is_nacho else GRN
        tag      = "NACHO" if is_nacho else "LOZ"
        pad_l    = 10 if is_nacho else 80
        pad_r    = 80 if is_nacho else 10

        row = tk.Frame(self._cf, bg=BG)
        row.pack(fill="x", pady=4, padx=(pad_l, pad_r))
        row._mid = mid

        # Header: role tag + action buttons
        top = tk.Frame(row, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text=tag, font=("Consolas", 8, "bold"),
                 fg=color, bg=BG).pack(side="left")

        # Delete ✕ (both roles)
        xb = tk.Label(top, text="✕", font=("Consolas", 8),
                       fg=DIM, bg=BG, cursor="hand2")
        xb.pack(side="right")
        xb.bind("<Button-1>", lambda e, m=mid, r=row: self._del_msg(m, r))
        xb.bind("<Enter>", lambda e: xb.config(fg=RED))
        xb.bind("<Leave>", lambda e: xb.config(fg=DIM))

        if not is_nacho:
            # LOZ messages get: Edit, Spell Check, AI Check
            for btn_text, btn_col, btn_fn in [
                ("🤖 check", PCH, lambda m=mid, t=text, r=row: self._ai_check(m, t, r)),
                ("🔤 spell", YEL, lambda m=mid, t=text, r=row: self._spell_check(m, t, r)),
                ("✏️ edit",  LAV, lambda m=mid, t=text, r=row: self._edit_msg(m, t, r)),
            ]:
                b = tk.Label(top, text=btn_text, font=("Segoe UI", 7),
                             fg=btn_col, bg=BG, cursor="hand2", padx=3)
                b.pack(side="right")
                b.bind("<Button-1>", lambda e, fn=btn_fn: fn())
                b.bind("<Enter>", lambda e, w=b, c=btn_col: w.config(fg=TEXT))
                b.bind("<Leave>", lambda e, w=b, c=btn_col: w.config(fg=c))

        # Text content frame (holds sentence links or edit widget)
        self._content_frame = tk.Frame(row, bg=BG)
        self._content_frame.pack(fill="x")
        row._content = self._content_frame

        self._fill_sentences(self._content_frame, text, color)

    def _fill_sentences(self, parent, text, color):
        """Render sentences as hyperlinks inside parent frame."""
        for w in parent.winfo_children():
            w.destroy()

        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if not sentences:
            sentences = [text]

        for sent in sentences:
            lk = tk.Label(parent, text=sent, font=("Segoe UI", 15),
                          fg=TEXT, bg=BG, wraplength=560,
                          justify="left", anchor="w", cursor="hand2")
            lk.pack(fill="x", pady=1)

            def _in(e, w=lk, c=color):
                w.config(font=("Segoe UI", 15, "underline"), fg=c)
            def _out(e, w=lk):
                w.config(font=("Segoe UI", 15), fg=TEXT)
            def _clk(e, s=sent):
                self._action_bar(s, e.x_root, e.y_root)

            lk.bind("<Enter>", _in)
            lk.bind("<Leave>", _out)
            lk.bind("<Button-1>", _clk)

    # ── Edit message (Loz only) ───────────────────────────────────────────
    def _edit_msg(self, mid, old_text, row):
        content = row._content
        for w in content.winfo_children():
            w.destroy()

        ef = tk.Frame(content, bg=BG)
        ef.pack(fill="x", pady=2)

        entry = tk.Text(ef, bg=CARD, fg=TEXT, insertbackground=LAV,
                        font=("Segoe UI", 13), wrap="word", relief="flat",
                        height=3, highlightbackground="#2a2a50",
                        highlightthickness=1)
        entry.insert("1.0", old_text)
        entry.pack(fill="x", pady=2)
        entry.focus_set()

        bf = tk.Frame(ef, bg=BG)
        bf.pack(fill="x")

        def _save():
            new_text = entry.get("1.0", "end").strip()
            if not new_text:
                return
            # Update message in list
            for m in self._msgs:
                if m["id"] == mid:
                    m["text"] = new_text
                    break
            # Re-render as sentences
            ef.destroy()
            self._fill_sentences(content, new_text, GRN)

        sb = tk.Label(bf, text="Save", bg=LAV, fg=BG,
                      font=("Segoe UI", 8, "bold"), padx=10, pady=2, cursor="hand2")
        sb.pack(side="left", padx=(0, 4))
        sb.bind("<Button-1>", lambda _: _save())

        cb = tk.Label(bf, text="Cancel", bg=CARD, fg=DIM,
                      font=("Segoe UI", 8), padx=8, pady=2, cursor="hand2")
        cb.pack(side="left")
        cb.bind("<Button-1>", lambda _: (ef.destroy(),
                                          self._fill_sentences(content, old_text, GRN)))

        entry.bind("<Control-Return>", lambda _: _save())

    # ── Spell check (quick local pass) ────────────────────────────────────
    def _spell_check(self, mid, text, row):
        self._stat.config(text="spell checking…", fg=YEL)
        api_key, model = _load_api()
        if not api_key:
            self._stat.config(text="no API key", fg=RED)
            return

        def _run():
            try:
                import anthropic
                cl = anthropic.Anthropic(api_key=api_key)
                r = cl.messages.create(
                    model=model, max_tokens=150,
                    messages=[{"role": "user", "content":
                        f"Fix ONLY spelling and grammar in this text. "
                        f"Return the corrected text only, nothing else:\n\n{text}"}])
                fixed = r.content[0].text.strip()
                self.root.after(0, self._apply_fix, mid, fixed, row)
            except Exception as e:
                self.root.after(0, lambda: self._stat.config(
                    text=f"spell error: {e}", fg=RED))

        threading.Thread(target=_run, daemon=True).start()

    # ── AI context check ──────────────────────────────────────────────────
    def _ai_check(self, mid, text, row):
        self._stat.config(text="AI checking…", fg=PCH)
        api_key, model = _load_api()
        if not api_key:
            self._stat.config(text="no API key", fg=RED)
            return

        def _run():
            try:
                import anthropic
                cl = anthropic.Anthropic(api_key=api_key)
                r = cl.messages.create(
                    model=model, max_tokens=200,
                    messages=[{"role": "user", "content":
                        f"This was spoken by someone with ADHD so the STT may have "
                        f"misheard words. Clean it up: fix mishearings, clarify intent, "
                        f"keep the same meaning and tone. Return corrected text only:\n\n{text}"}])
                fixed = r.content[0].text.strip()
                self.root.after(0, self._apply_fix, mid, fixed, row)
            except Exception as e:
                self.root.after(0, lambda: self._stat.config(
                    text=f"check error: {e}", fg=RED))

        threading.Thread(target=_run, daemon=True).start()

    def _apply_fix(self, mid, new_text, row):
        for m in self._msgs:
            if m["id"] == mid:
                m["text"] = new_text
                break
        content = row._content
        self._fill_sentences(content, new_text, GRN)
        self._stat.config(text="✓ fixed", fg=GRN)

    # ── Delete message ────────────────────────────────────────────────────
    def _del_msg(self, mid, widget):
        self._msgs = [m for m in self._msgs if m["id"] != mid]
        widget.destroy()

    # ── Wrong / retry (on NACHO messages) ─────────────────────────────────
    def _wrong_retry(self, mid, widget):
        """Delete NACHO's reply and re-run Claude on the last user message."""
        # Remove this NACHO message
        self._msgs = [m for m in self._msgs if m["id"] != mid]
        widget.destroy()

        # Find the last user message to retry against
        last_user = None
        for m in reversed(self._msgs):
            if m["role"] == "loz":
                last_user = m["text"]
                break

        if last_user:
            self._stat.config(text="retrying…", fg=PCH)
            threading.Thread(target=self._call_claude, args=(last_user,),
                             daemon=True).start()
        else:
            self._stat.config(text="no user message to retry", fg=DIM)

    # ── Action bar ────────────────────────────────────────────────────────
    def _action_bar(self, text, x, y):
        if self._abar:
            try: self._abar.destroy()
            except: pass

        bar = tk.Toplevel(self.root)
        bar.overrideredirect(True)
        bar.attributes("-topmost", True)
        bar.attributes("-alpha", 0.97)
        bar.configure(bg=BG2)
        self._abar = bar
        bar.geometry(f"+{x}+{y+8}")

        short = text[:35] + "…" if len(text) > 35 else text
        tk.Label(bar, text=f' "{short}" ',
                 font=("Segoe UI", 7), fg=DIM, bg=BG2).pack(
                     fill="x", padx=4, pady=(3, 0))

        bf = tk.Frame(bar, bg=BG2)
        bf.pack(padx=3, pady=3)

        # Find which message this sentence belongs to (for delete/wrong)
        owner_mid   = None
        owner_row   = None
        owner_role  = None
        for m in self._msgs:
            if text in m["text"]:
                owner_mid  = m["id"]
                owner_role = m["role"]
                break
        if owner_mid:
            for w in self._cf.winfo_children():
                if hasattr(w, "_mid") and w._mid == owner_mid:
                    owner_row = w
                    break

        acts = [
            ("📋", "Copy",     lambda: self._copy(text)),
            ("📧", "Email",    lambda: self._email(text)),
            ("✈️", "Telegram", lambda: self._telegram(text)),
            ("💬", "Thread",   lambda: self._thread(text)),
            ("🤖", "Claude",   lambda: self._claude(text)),
            ("🖊️", "CodePen",  lambda: self._codepen(text)),
            ("📝", "Note",     lambda: self._note(text)),
            ("🔗", "Linker",   lambda: self._linker(text)),
        ]

        # Delete: removes the whole message this sentence belongs to
        if owner_mid and owner_row:
            acts.append(("🗑", "Delete",
                lambda m=owner_mid, r=owner_row: self._del_msg(m, r)))

        # Wrong: only on NACHO messages — retry with different answer
        if owner_role == "nacho" and owner_mid and owner_row:
            acts.append(("❌", "Wrong",
                lambda m=owner_mid, r=owner_row: self._wrong_retry(m, r)))
        for em, lb, fn in acts:
            b = tk.Label(bf, text=f"{em} {lb}", font=("Segoe UI", 8),
                         fg=TEXT, bg=CARD, padx=6, pady=3, cursor="hand2")
            b.pack(side="left", padx=1)
            b.bind("<Enter>", lambda e, w=b: w.config(bg=LAV, fg=BG))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=CARD, fg=TEXT))
            b.bind("<Button-1>", lambda e, f=fn: (f(), bar.destroy()))

        bar.after(7000, lambda: bar.destroy() if bar.winfo_exists() else None)

    # ── Actions ───────────────────────────────────────────────────────────
    def _copy(self, t):
        self.root.clipboard_clear(); self.root.clipboard_append(t)
        self._stat.config(text="copied", fg=GRN)

    def _email(self, t):
        import urllib.parse as up
        os.startfile(f"mailto:?subject={up.quote('From NACHO')}&body={up.quote(t)}")

    def _telegram(self, t):
        self.root.clipboard_clear()
        self.root.clipboard_append(t)
        self.root.update()
        self._stat.config(text="copied — paste into Telegram", fg=TEAL)
        # Open Telegram desktop (user pastes into their chosen chat)
        try: os.startfile("tg://")
        except: pass

    def _thread(self, t):
        self._add("loz", f"Let's talk about: {t}")
        self._stat.config(text="thinking…", fg=PCH)
        threading.Thread(target=self._call_claude,
                         args=(f"Let's talk about: {t}",), daemon=True).start()

    def _claude(self, t):
        self._copy(t)
        try: subprocess.Popen(["claude"], creationflags=0x8, shell=True)
        except: pass

    def _codepen(self, t):
        import webbrowser, urllib.parse as up
        webbrowser.open(f"https://codepen.io/pen/?html={up.quote(t)}")

    def _note(self, t):
        LOG_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        p  = LOG_DIR / f"note_{ts}.md"
        p.write_text(f"# NACHO Note — {datetime.now():%Y-%m-%d %H:%M}\n\n{t}\n",
                     encoding="utf-8")
        self._stat.config(text=f"saved: {p.name}", fg=GRN)

    def _linker(self, t):
        lc = SCRIPT_DIR / "linker_config.json"
        if not lc.exists(): return
        try:
            cfg = json.loads(lc.read_text(encoding="utf-8"))
            for cat in cfg.get("categories", []):
                if cat.get("_pinned_bucket"): continue
                exists = [p["text"] if isinstance(p, dict) else p
                          for p in cat["phrases"]]
                if t not in exists:
                    cat["phrases"].append({"text": t, "emoji": "💬", "image": None})
                lc.write_text(json.dumps(cfg, indent=2, ensure_ascii=False),
                              encoding="utf-8")
                self._stat.config(text=f"→ Linker: {cat['name']}", fg=GRN)
                return
        except: pass

    # ── Export ────────────────────────────────────────────────────────────
    def _export(self):
        if not self._msgs:
            self._stat.config(text="nothing to export", fg=DIM)
            return
        LOG_DIR.mkdir(exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = LOG_DIR / f"chat_{ts}.md"
        lines = [f"# NACHO Chat — {datetime.now():%Y-%m-%d %H:%M}\n\n"]
        for m in self._msgs:
            lines.append(f"**{m['role'].upper()}:** {m['text']}\n\n")
        path.write_text("".join(lines), encoding="utf-8")

        # Also copy full text to clipboard
        flat = "\n".join(f"[{m['role'].upper()}] {m['text']}" for m in self._msgs)
        self.root.clipboard_clear()
        self.root.clipboard_append(flat)
        self._stat.config(text=f"exported + copied: {path.name}", fg=GRN)

    # ── Voice flow ────────────────────────────────────────────────────────
    def _greet(self):
        self._add("nacho", GREETING)
        self._stat.config(text="speaking…", fg=MAU)
        speak(GREETING, done_cb=lambda: self.root.after(0, self._listen))

    def _listen(self):
        self._stat.config(text="🎙️ listening…", fg=GRN)
        self._mb.config(text="🎙️  Listening…", fg=YEL)
        if not self._mic:
            self._mic = Mic(
                on_final=lambda t: self.root.after(0, self._heard, t),
                on_partial=lambda t: self.root.after(0,
                    lambda: self._stat.config(
                        text=f"…{t[-40:]}", fg=YEL)))
        self._mic.start()

    def _heard(self, text):
        self._mb.config(text="🎙️  Tap to speak", fg=GRN)
        if not text:
            self._stat.config(text="didn't catch that", fg=DIM)
            return

        self._add("loz", text)

        # Dismiss keywords
        if any(k in text.lower() for k in ["bye","dismiss","later","close","shut up"]):
            bye = "Catch you later, Loz."
            self._add("nacho", bye)
            speak(bye, done_cb=lambda: self.root.after(0, self._close))
            return

        self._stat.config(text="thinking…", fg=PCH)
        threading.Thread(target=self._call_claude, args=(text,), daemon=True).start()

    def _call_claude(self, user_text):
        api_key, model = _load_api()
        if not api_key:
            self.root.after(0, self._add, "nacho", "No API key set.")
            return
        try:
            import anthropic
            cl  = anthropic.Anthropic(api_key=api_key)
            msgs = []
            for m in self._msgs[-16:]:
                if m["role"] == "loz":
                    msgs.append({"role": "user", "content": m["text"]})
                elif m["role"] == "nacho":
                    msgs.append({"role": "assistant", "content": m["text"]})
            r = cl.messages.create(model=model, max_tokens=150,
                                   system=SYS_PROMPT, messages=msgs)
            reply = r.content[0].text.strip()
        except Exception as e:
            reply = f"Brain glitch: {e}"

        self.root.after(0, self._deliver, reply)

    def _deliver(self, reply):
        self._add("nacho", reply)
        self._stat.config(text="speaking…", fg=MAU)
        speak(reply, done_cb=lambda: self.root.after(0, self._listen))

    # ── Close ─────────────────────────────────────────────────────────────
    def _close(self):
        if self._mic: self._mic.stop()
        # Auto-export on close if there's content
        if len(self._msgs) > 1:
            self._export()
        try: self._ovl.destroy()
        except: pass

    # ── Tray ──────────────────────────────────────────────────────────────
    def _start_tray(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d   = ImageDraw.Draw(img)
        d.rounded_rectangle([4, 4, 59, 59], radius=12, fill=(203, 166, 247))
        try:    fnt = ImageFont.truetype("consola.ttf", 20)
        except: fnt = ImageFont.load_default()
        bb = d.textbbox((0, 0), "NA", font=fnt)
        d.text(((64-(bb[2]-bb[0]))//2, (64-(bb[3]-bb[1]))//2),
               "NA", fill="#0a0a14", font=fnt)
        import pystray
        menu = pystray.Menu(
            pystray.MenuItem("Open",    lambda: self.root.after(0, self._reopen)),
            pystray.MenuItem("Restart", lambda: self.root.after(0, self._restart)),
            pystray.MenuItem("Quit",    lambda: self.root.after(0, self._quit)),
        )
        self._tray = pystray.Icon("nacho", img, "NACHO", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _reopen(self):
        try: self._ovl.deiconify(); self._ovl.lift()
        except: self._build(); self._greet()

    def _restart(self):
        if self._mic: self._mic.stop()
        subprocess.Popen([str(PYTHONW), str(SCRIPT_DIR / "nacho.py")],
                         creationflags=0x8, cwd=str(SCRIPT_DIR))
        self._quit()

    def _quit(self):
        if self._mic: self._mic.stop()
        if hasattr(self, "_tray") and self._tray: self._tray.stop()
        try: self.root.destroy()
        except: pass


if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("nacho.py")
    NachoApp()
