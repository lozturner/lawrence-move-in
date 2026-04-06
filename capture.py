"""
Lawrence: Move In — Capture v3.0.0
Full-featured session-based screenshot capture tool.
Double-click tray = instant capture. Right-click = menu.
Every capture has: save, share, ID, session context, export, settings, hub link.
"""
__version__ = "3.0.0"

import base64, io, json, os, subprocess, sys, threading, time, tkinter as tk
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import mss, pystray, win32clipboard
from PIL import Image, ImageDraw, ImageFont, ImageTk

SCRIPT_DIR   = Path(__file__).resolve().parent
SESSIONS_DIR = SCRIPT_DIR / "capture_sessions"
API_CFG      = SCRIPT_DIR / "kidlin_config.json"
PYTHONW      = Path(sys.executable).with_name("pythonw.exe")

BG="#0a0a14";BG2="#12122a";CARD="#1a1a3a";CARD_HI="#252545";BORDER="#2a2a50"
TEXT="#cdd6f4";DIM="#5a5a80";LAV="#b4befe";GRN="#a6e3a1";PCH="#fab387"
MAU="#cba6f7";RED="#f38ba8";TEAL="#94e2d5";YEL="#f9e2af";BLUE="#89b4fa"

def load_api():
    try:
        d=json.loads(API_CFG.read_text())
        return d.get("api_key",""),d.get("model","claude-sonnet-4-20250514")
    except: return "","claude-sonnet-4-20250514"

def screenshot():
    with mss.mss() as s:
        r=s.grab(s.monitors[0])
        img=Image.frombytes("RGB",r.size,r.bgra,"raw","BGRX")
    if img.width>1280:
        ra=1280/img.width; img=img.resize((1280,int(img.height*ra)),Image.LANCZOS)
    return img

def img_b64(img,q=65):
    b=io.BytesIO(); img.save(b,format="JPEG",quality=q)
    return base64.b64encode(b.getvalue()).decode()

def clip(text):
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text)
        win32clipboard.CloseClipboard()
    except:
        try: win32clipboard.CloseClipboard()
        except: pass

# ── Session ──────────────────────────────────────────────────────────────────
class Session:
    def __init__(self, load_dir=None):
        if load_dir:
            self.dir = Path(load_dir)
            d = json.loads((self.dir/"session.json").read_text(encoding="utf-8"))
            self.uid = d["session_uid"]
            self.started = datetime.fromisoformat(d["started"])
            self.captures = d["captures"]
        else:
            self.uid = uuid4().hex[:6].upper()
            self.started = datetime.now()
            self.dir = SESSIONS_DIR/f"{self.started:%Y%m%d_%H%M%S}_{self.uid}"
            self.dir.mkdir(parents=True,exist_ok=True)
            (self.dir/"screenshots").mkdir(exist_ok=True)
            self.captures = []

    def add(self, img):
        idx = len(self.captures)+1
        fn = f"{idx:03d}.jpg"
        img.save(self.dir/"screenshots"/fn, format="JPEG", quality=80)
        rec = {"idx":idx, "uid":uuid4().hex[:8].upper(),
               "timestamp":datetime.now().isoformat(),
               "screenshot":fn, "notes":"", "ai_summary":"", "tags":[]}
        self.captures.append(rec)
        self.save()
        return rec

    def get(self, idx):
        for c in self.captures:
            if c["idx"]==idx: return c
        return None

    def update(self, idx, **kw):
        for c in self.captures:
            if c["idx"]==idx:
                c.update(kw)
                break
        self.save()

    def delete(self, idx):
        self.captures = [c for c in self.captures if c["idx"]!=idx]
        self.save()

    def save(self):
        (self.dir/"session.json").write_text(json.dumps({
            "session_uid":self.uid, "started":self.started.isoformat(),
            "capture_count":len(self.captures), "captures":self.captures
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    def compile(self):
        out = {"session_uid":self.uid,"started":self.started.isoformat(),
               "ended":datetime.now().isoformat(),
               "capture_count":len(self.captures),"captures":self.captures}
        (self.dir/"compiled.json").write_text(
            json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
        md = [f"# Session {self.uid} — {self.started:%Y-%m-%d %H:%M}\n\n"]
        for c in self.captures:
            md.append(f"## #{c['idx']} {c['uid']} — {c['timestamp'][:19]}\n")
            md.append(f"![](screenshots/{c['screenshot']})\n")
            if c["notes"]: md.append(f"**Notes:** {c['notes']}\n")
            if c["ai_summary"]: md.append(f"**AI:** {c['ai_summary']}\n")
            if c["tags"]: md.append(f"**Tags:** {', '.join(c['tags'])}\n")
            md.append("\n---\n\n")
        (self.dir/"compiled.md").write_text("".join(md),encoding="utf-8")
        prompt = self._build_prompt()
        (self.dir/"ai_prompt.txt").write_text(prompt,encoding="utf-8")
        return out, prompt

    def _build_prompt(self):
        p = f"Capture session {self.uid}, {len(self.captures)} screenshots.\n"
        p += f"Started {self.started:%Y-%m-%d %H:%M}.\n\n"
        p += "Analyze: what was I doing, what was the flow, suggested next steps.\n\n"
        for c in self.captures:
            p += f"[#{c['idx']}] {c['timestamp'][:19]}"
            if c["notes"]: p += f" — {c['notes']}"
            p += "\n"
        return p


# ── Main App ─────────────────────────────────────────────────────────────────
class CaptureApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.session = None
        self._main_win = None
        self._photos = []
        self._start_tray()
        self.root.mainloop()

    def _ensure_session(self):
        if not self.session:
            self.session = Session()

    # ── Quick capture (double-click tray) ─────────────────────────────────
    def _quick_capture(self):
        self._ensure_session()
        img = screenshot()
        rec = self.session.add(img)
        self._open_main(focus_idx=rec["idx"])

    # ── Main Window ───────────────────────────────────────────────────────
    def _open_main(self, focus_idx=None):
        if self._main_win and self._main_win.winfo_exists():
            self._main_win.lift()
            if focus_idx:
                self._show_capture(focus_idx)
            return

        w = tk.Toplevel(self.root)
        w.title(f"Capture v{__version__}")
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.97)
        w.configure(bg=BG)
        self._main_win = w

        sw,sh = w.winfo_screenwidth(), w.winfo_screenheight()
        ww,wh = min(900,sw-40), min(650,sh-60)
        w.geometry(f"{ww}x{wh}+{(sw-ww)//2}+{(sh-wh)//2}")

        # ── Top bar ──────────────────────────────────────────────────
        top = tk.Frame(w, bg=BG2)
        top.pack(fill="x")

        tk.Label(top, text="  📸 Capture", font=("Consolas",12,"bold"),
                 fg=PCH, bg=BG2).pack(side="left", padx=6, ipady=8)

        self._session_lbl = tk.Label(top, text="", font=("Segoe UI",8),
                                     fg=DIM, bg=BG2)
        self._session_lbl.pack(side="left", padx=8)

        for txt, col, cmd in [
            ("✕", RED, lambda: w.destroy()),
            ("⚙ Settings", DIM, self._settings),
            ("🏠 Hub", LAV, lambda: subprocess.Popen(
                [str(PYTHONW), str(SCRIPT_DIR/"hub.py")], creationflags=0x8)),
        ]:
            b = tk.Label(top, text=f" {txt} ", font=("Segoe UI",9),
                         fg=col, bg=BG2, cursor="hand2")
            b.pack(side="right", padx=3)
            b.bind("<Button-1>", lambda e,fn=cmd: fn())

        # ── Body: sidebar + main panel ────────────────────────────────
        body = tk.Frame(w, bg=BG)
        body.pack(fill="both", expand=True)

        # Sidebar: session captures list
        self._sidebar = tk.Frame(body, bg=CARD, width=200)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        sb_hdr = tk.Frame(self._sidebar, bg=BG2)
        sb_hdr.pack(fill="x")
        tk.Label(sb_hdr, text=" Session", font=("Segoe UI",8,"bold"),
                 fg=LAV, bg=BG2).pack(side="left", padx=6, ipady=4)

        # Sidebar buttons
        sb_btns = tk.Frame(self._sidebar, bg=CARD)
        sb_btns.pack(fill="x", padx=4, pady=4)
        for txt, fn in [
            ("📸 New Capture", self._quick_capture),
            ("🔚 End Session", self._end_session),
            ("📂 New Session", self._new_session),
            ("📤 Export All", self._export_session),
        ]:
            b = tk.Label(sb_btns, text=txt, font=("Segoe UI",8),
                         fg=TEXT, bg=BG2, padx=6, pady=3, cursor="hand2", anchor="w")
            b.pack(fill="x", pady=1)
            b.bind("<Button-1>", lambda e,f=fn: f())
            b.bind("<Enter>", lambda e,w=b: w.config(bg=CARD_HI))
            b.bind("<Leave>", lambda e,w=b: w.config(bg=BG2))

        # Capture list (scrollable)
        self._cap_list_frame = tk.Frame(self._sidebar, bg=CARD)
        self._cap_list_frame.pack(fill="both", expand=True, padx=4)

        # Main panel
        self._panel = tk.Frame(body, bg=BG)
        self._panel.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        self._refresh_sidebar()
        if focus_idx:
            self._show_capture(focus_idx)
        elif self.session and self.session.captures:
            self._show_capture(self.session.captures[-1]["idx"])
        else:
            self._show_empty()

    def _refresh_sidebar(self):
        for w in self._cap_list_frame.winfo_children():
            w.destroy()

        if not self.session:
            return

        self._session_lbl.config(
            text=f"Session {self.session.uid}  •  {len(self.session.captures)} captures")

        for c in reversed(self.session.captures):
            f = tk.Frame(self._cap_list_frame, bg=BG2, cursor="hand2")
            f.pack(fill="x", pady=1)

            tk.Label(f, text=f"#{c['idx']}", font=("Consolas",9,"bold"),
                     fg=PCH, bg=BG2, padx=4).pack(side="left")
            tk.Label(f, text=c["uid"], font=("Consolas",7),
                     fg=DIM, bg=BG2, padx=2).pack(side="left")
            tk.Label(f, text=c["timestamp"][11:19], font=("Consolas",7),
                     fg=DIM, bg=BG2).pack(side="right", padx=4)

            if c["notes"]:
                tk.Label(f, text="📝", font=("Segoe UI",7),
                         bg=BG2).pack(side="right")

            for w in f.winfo_children():
                w.bind("<Button-1>", lambda e,idx=c["idx"]: self._show_capture(idx))
            f.bind("<Button-1>", lambda e,idx=c["idx"]: self._show_capture(idx))
            f.bind("<Enter>", lambda e,fr=f: [w.config(bg=CARD_HI) for w in [fr]+list(fr.winfo_children())])
            f.bind("<Leave>", lambda e,fr=f: [w.config(bg=BG2) for w in [fr]+list(fr.winfo_children())])

    def _show_empty(self):
        for w in self._panel.winfo_children(): w.destroy()
        tk.Label(self._panel, text="📸", font=("Segoe UI Emoji",48),
                 bg=BG).pack(expand=True)
        tk.Label(self._panel, text="Double-click tray icon to capture\nor click 📸 New Capture",
                 font=("Segoe UI",11), fg=DIM, bg=BG).pack()

    def _show_capture(self, idx):
        for w in self._panel.winfo_children(): w.destroy()
        self._photos.clear()

        if not self.session: return
        rec = self.session.get(idx)
        if not rec: return

        # ── Header row: ID + tags + delete ────────────────────────────
        hdr = tk.Frame(self._panel, bg=BG)
        hdr.pack(fill="x", pady=(0,4))

        tk.Label(hdr, text=f"#{rec['idx']}", font=("Consolas",14,"bold"),
                 fg=PCH, bg=BG).pack(side="left")
        tk.Label(hdr, text=rec["uid"], font=("Consolas",10),
                 fg=DIM, bg=BG, padx=8).pack(side="left")
        tk.Label(hdr, text=f"Session {self.session.uid}",
                 font=("Segoe UI",8), fg=LAV, bg=BG, padx=8).pack(side="left")
        tk.Label(hdr, text=rec["timestamp"][:19],
                 font=("Consolas",8), fg=DIM, bg=BG).pack(side="left")

        # Delete
        db = tk.Label(hdr, text="🗑", font=("Segoe UI",10),
                      fg=RED, bg=BG, cursor="hand2", padx=4)
        db.pack(side="right")
        db.bind("<Button-1>", lambda e: self._delete_capture(idx))

        # ── Screenshot ────────────────────────────────────────────────
        img_path = self.session.dir/"screenshots"/rec["screenshot"]
        if img_path.exists():
            img = Image.open(img_path)
            max_w = min(650, self._panel.winfo_width()-20) or 650
            if img.width > max_w:
                r = max_w/img.width
                img = img.resize((max_w, int(img.height*r)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._photos.append(photo)
            tk.Label(self._panel, image=photo, bg="#000").pack(pady=(0,4))

        # ── Notes ─────────────────────────────────────────────────────
        nf = tk.Frame(self._panel, bg=CARD)
        nf.pack(fill="x", pady=(0,4))
        tk.Label(nf, text=" Notes", font=("Segoe UI",8,"bold"),
                 fg=TEAL, bg=CARD).pack(anchor="w", padx=6, pady=(4,0))
        txt = tk.Text(nf, bg=BG2, fg=TEXT, insertbackground=LAV,
                      font=("Segoe UI",10), wrap="word", height=3,
                      relief="flat", highlightthickness=0)
        txt.pack(fill="x", padx=6, pady=4)
        if rec["notes"]:
            txt.insert("1.0", rec["notes"])

        # Save notes button
        def _save_notes():
            notes = txt.get("1.0","end").strip()
            self.session.update(idx, notes=notes)
            self._refresh_sidebar()
            self._flash("Notes saved")

        # ── AI Summary ────────────────────────────────────────────────
        ai_frame = tk.Frame(self._panel, bg=CARD)
        ai_frame.pack(fill="x", pady=(0,4))
        tk.Label(ai_frame, text=" AI Summary", font=("Segoe UI",8,"bold"),
                 fg=MAU, bg=CARD).pack(anchor="w", padx=6, pady=(4,0))
        self._ai_lbl = tk.Label(ai_frame, text=rec.get("ai_summary","") or "Not yet analyzed",
                                font=("Segoe UI",9), fg=DIM if not rec.get("ai_summary") else TEXT,
                                bg=CARD, wraplength=600, justify="left", anchor="nw",
                                padx=6, pady=4)
        self._ai_lbl.pack(fill="x")

        # ── Action buttons ────────────────────────────────────────────
        af = tk.Frame(self._panel, bg=BG)
        af.pack(fill="x", pady=(4,0))

        actions = [
            ("💾 Save Notes", GRN,   _save_notes),
            ("🤖 AI Analyze", MAU,   lambda: self._ai_single(idx, img_path)),
            ("📋 Copy ID",    LAV,   lambda: clip(f"[Capture {rec['uid']}] Session {self.session.uid}")),
            ("📧 Email",      BLUE,  lambda: self._share_email(rec)),
            ("✈️ Telegram",   TEAL,  lambda: self._share_telegram(rec)),
            ("📋 Copy All",   PCH,   lambda: self._copy_capture(rec)),
            ("📤 Export",     YEL,   lambda: self._export_single(rec)),
        ]

        for txt, col, fn in actions:
            b = tk.Label(af, text=txt, font=("Segoe UI",8),
                         fg=col, bg=CARD, padx=6, pady=4, cursor="hand2")
            b.pack(side="left", padx=1)
            b.bind("<Button-1>", lambda e,f=fn: f())
            b.bind("<Enter>", lambda e,w=b: w.config(bg=CARD_HI))
            b.bind("<Leave>", lambda e,w=b: w.config(bg=CARD))

        # Nav: prev/next
        nf2 = tk.Frame(self._panel, bg=BG)
        nf2.pack(fill="x", pady=(6,0))
        if idx > 1:
            pb = tk.Label(nf2, text="← Previous", font=("Segoe UI",8),
                          fg=DIM, bg=BG, cursor="hand2")
            pb.pack(side="left")
            pb.bind("<Button-1>", lambda e: self._show_capture(idx-1))
        idxs = [c["idx"] for c in self.session.captures]
        if idx < max(idxs) if idxs else 0:
            nb = tk.Label(nf2, text="Next →", font=("Segoe UI",8),
                          fg=DIM, bg=BG, cursor="hand2")
            nb.pack(side="right")
            nb.bind("<Button-1>", lambda e: self._show_capture(idx+1))

    # ── Actions ───────────────────────────────────────────────────────────
    def _delete_capture(self, idx):
        self.session.delete(idx)
        self._refresh_sidebar()
        if self.session.captures:
            self._show_capture(self.session.captures[-1]["idx"])
        else:
            self._show_empty()

    def _ai_single(self, idx, img_path):
        api_key, model = load_api()
        if not api_key:
            self._ai_lbl.config(text="No API key in kidlin_config.json", fg=RED)
            return
        self._ai_lbl.config(text="Analyzing…", fg=YEL)

        def _run():
            try:
                import anthropic
                img = Image.open(img_path)
                b64 = img_b64(img)
                cl = anthropic.Anthropic(api_key=api_key)
                rec = self.session.get(idx)
                notes = rec.get("notes","") if rec else ""
                prompt = "What is on this screen? Be specific — read text, identify apps, describe what the user is doing. 2-3 sentences."
                if notes:
                    prompt += f"\nUser's notes: {notes}"
                r = cl.messages.create(model=model, max_tokens=200,
                    messages=[{"role":"user","content":[
                        {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}},
                        {"type":"text","text":prompt}]}])
                summary = r.content[0].text.strip()
                self.session.update(idx, ai_summary=summary)
                self.root.after(0, lambda: self._ai_lbl.config(text=summary, fg=TEXT))
            except Exception as e:
                self.root.after(0, lambda: self._ai_lbl.config(text=f"Error: {e}", fg=RED))

        threading.Thread(target=_run, daemon=True).start()

    def _share_email(self, rec):
        import urllib.parse as up
        subj = up.quote(f"Capture {rec['uid']} — Session {self.session.uid}")
        body = up.quote(f"Capture #{rec['idx']} ({rec['uid']})\n{rec['timestamp'][:19]}\n\n{rec.get('notes','')}\n\nAI: {rec.get('ai_summary','')}")
        os.startfile(f"mailto:?subject={subj}&body={body}")

    def _share_telegram(self, rec):
        text = f"[Capture {rec['uid']}] #{rec['idx']}\n{rec.get('notes','')}"
        if rec.get("ai_summary"): text += f"\nAI: {rec['ai_summary']}"
        clip(text)
        try: os.startfile("tg://")
        except: pass
        self._flash("Copied — paste into Telegram")

    def _copy_capture(self, rec):
        text = f"[Capture {rec['uid']}] Session {self.session.uid}\n"
        text += f"#{rec['idx']} — {rec['timestamp'][:19]}\n"
        if rec["notes"]: text += f"Notes: {rec['notes']}\n"
        if rec.get("ai_summary"): text += f"AI: {rec['ai_summary']}\n"
        text += f"File: {self.session.dir/'screenshots'/rec['screenshot']}"
        clip(text)
        self._flash("Copied to clipboard")

    def _export_single(self, rec):
        md = f"# Capture {rec['uid']}\n\n"
        md += f"**Session:** {self.session.uid}\n"
        md += f"**Time:** {rec['timestamp'][:19]}\n\n"
        if rec["notes"]: md += f"## Notes\n\n{rec['notes']}\n\n"
        if rec.get("ai_summary"): md += f"## AI Summary\n\n{rec['ai_summary']}\n\n"
        md += f"![](screenshots/{rec['screenshot']})\n"
        path = self.session.dir/f"capture_{rec['uid']}.md"
        path.write_text(md, encoding="utf-8")
        clip(md)
        self._flash(f"Exported: {path.name}")

    # ── Session actions ───────────────────────────────────────────────────
    def _end_session(self):
        if not self.session or not self.session.captures:
            self._flash("No captures to compile")
            return
        out, prompt = self.session.compile()
        clip(prompt)
        # AI summary of full session
        api_key, model = load_api()
        if api_key:
            self._ai_session(api_key, model, out, prompt)
        else:
            self._show_end_popup(None, prompt)

    def _ai_session(self, api_key, model, out, prompt):
        session = self.session
        def _run():
            try:
                import anthropic
                cl = anthropic.Anthropic(api_key=api_key)
                content = []
                for c in session.captures[:8]:
                    p = session.dir/"screenshots"/c["screenshot"]
                    if p.exists():
                        content.append({"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":img_b64(Image.open(p))}})
                        if c["notes"]:
                            content.append({"type":"text","text":f"[#{c['idx']}] {c['notes']}"})
                content.append({"type":"text","text":"Summarize this capture session: what was the user doing, what was the flow, any observations, suggested next steps. 4-6 sentences."})
                r = cl.messages.create(model=model, max_tokens=400,
                    messages=[{"role":"user","content":content}])
                summary = r.content[0].text.strip()
            except Exception as e:
                summary = f"AI error: {e}"
            self.root.after(0, lambda: self._show_end_popup(summary, prompt))
        threading.Thread(target=_run, daemon=True).start()
        self._flash("Compiling session…")

    def _show_end_popup(self, ai_summary, prompt):
        s = self.session
        dlg = tk.Toplevel(self.root)
        dlg.title(f"Session {s.uid} — Complete")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=BG)
        sw,sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"600x450+{(sw-600)//2}+{(sh-450)//2}")

        tk.Label(dlg, text=f"  ✅ Session {s.uid} compiled", bg=BG2, fg=GRN,
                 font=("Consolas",11,"bold"), anchor="w").pack(fill="x", ipady=8)

        sf = tk.Frame(dlg, bg=CARD)
        sf.pack(fill="x", padx=12, pady=8)
        for lbl, val, col in [("Captures",str(len(s.captures)),PCH),
                                ("Duration",f"{(datetime.now()-s.started).seconds//60}min",BLUE),
                                ("Folder",s.dir.name[:20],DIM)]:
            f = tk.Frame(sf, bg=CARD, padx=12, pady=4)
            f.pack(side="left")
            tk.Label(f, text=val, font=("Consolas",13,"bold"), fg=col, bg=CARD).pack()
            tk.Label(f, text=lbl, font=("Segoe UI",7), fg=DIM, bg=CARD).pack()

        if ai_summary:
            tk.Label(dlg, text="AI Session Summary", font=("Segoe UI",9,"bold"),
                     fg=MAU, bg=BG, anchor="w").pack(fill="x", padx=14, pady=(8,2))
            tk.Label(dlg, text=ai_summary, font=("Segoe UI",10), fg=TEXT, bg=CARD,
                     wraplength=560, justify="left", anchor="nw",
                     padx=10, pady=8).pack(fill="x", padx=12)

        tk.Label(dlg, text="Files: compiled.md, compiled.json, ai_prompt.txt",
                 font=("Consolas",7), fg=DIM, bg=BG).pack(pady=(8,2))
        tk.Label(dlg, text="AI prompt copied to clipboard — paste into any LLM",
                 font=("Segoe UI",8), fg=YEL, bg=BG).pack(pady=2)

        bf = tk.Frame(dlg, bg=BG)
        bf.pack(fill="x", padx=12, pady=8)
        for txt, fn in [("📋 Copy prompt", lambda: clip(prompt)),
                         ("📋 Copy JSON", lambda: clip(json.dumps(
                             json.loads((s.dir/"compiled.json").read_text()),indent=2))),
                         ("📁 Open folder", lambda: os.startfile(str(s.dir))),
                         ("Close", lambda: dlg.destroy())]:
            b = tk.Label(bf, text=f" {txt} ", font=("Segoe UI",8),
                         fg=TEXT, bg=CARD, padx=6, pady=3, cursor="hand2")
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e,f=fn: f())

        # Start fresh
        self.session = None
        self._refresh_sidebar()

    def _new_session(self):
        if self.session and self.session.captures:
            self._end_session()
        self.session = Session()
        self._refresh_sidebar()
        self._show_empty()
        self._flash(f"New session {self.session.uid}")

    def _export_session(self):
        if not self.session or not self.session.captures:
            self._flash("Nothing to export")
            return
        out, prompt = self.session.compile()
        clip(prompt)
        self._flash("Session exported + prompt copied")

    # ── Settings ──────────────────────────────────────────────────────────
    def _settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Capture Settings")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=BG)
        dlg.geometry("300x200")

        tk.Label(dlg, text="  ⚙ Capture Settings", bg=BG2, fg=LAV,
                 font=("Segoe UI",10,"bold"), anchor="w").pack(fill="x", ipady=8)

        tk.Label(dlg, text="Session folder:", font=("Segoe UI",8), fg=DIM,
                 bg=BG, anchor="w").pack(fill="x", padx=12, pady=(8,0))
        tk.Label(dlg, text=str(SESSIONS_DIR), font=("Consolas",7), fg=TEXT,
                 bg=CARD, anchor="w", padx=6, pady=4).pack(fill="x", padx=12)

        tk.Label(dlg, text=f"API key: {'✅ set' if load_api()[0] else '❌ not set'}",
                 font=("Segoe UI",9), fg=GRN if load_api()[0] else RED,
                 bg=BG, anchor="w").pack(fill="x", padx=12, pady=(8,0))

        bf = tk.Frame(dlg, bg=BG)
        bf.pack(fill="x", padx=12, pady=12)
        for txt, fn in [("📂 Open sessions folder", lambda: os.startfile(str(SESSIONS_DIR))),
                         ("Close", lambda: dlg.destroy())]:
            b = tk.Label(bf, text=txt, font=("Segoe UI",8), fg=TEXT, bg=CARD,
                         padx=8, pady=3, cursor="hand2")
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e,f=fn: f())

    # ── Flash ─────────────────────────────────────────────────────────────
    def _flash(self, text):
        try:
            self._session_lbl.config(text=text, fg=GRN)
            self.root.after(2500, lambda: self._session_lbl.config(
                text=f"Session {self.session.uid}  •  {len(self.session.captures)} captures"
                if self.session else "No session", fg=DIM))
        except: pass

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

        def _slbl(_):
            if self.session and self.session.captures:
                return f"Session {self.session.uid}: {len(self.session.captures)} captures"
            return "No active session"

        menu = pystray.Menu(
            pystray.MenuItem(_slbl, lambda i,it: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📸 Capture Now",
                lambda i,it: self.root.after(0, self._quick_capture)),
            pystray.MenuItem("🔚 End Session",
                lambda i,it: self.root.after(0, self._end_session)),
            pystray.MenuItem("📂 New Session",
                lambda i,it: self.root.after(0, self._new_session)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Capture Window",
                lambda i,it: self.root.after(0, lambda: self._open_main())),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",
                lambda i,it: self._quit(i)),
        )
        self._tray = pystray.Icon("capture", img, "Capture", menu)
        # Double-click tray = instant capture + open main window
        self._tray.default_action = lambda i,it: self.root.after(0, self._quick_capture)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _quit(self, icon=None):
        if self.session and self.session.captures:
            self.session.compile()
        if icon: icon.stop()
        try: self.root.destroy()
        except: pass

if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("capture.py")
    CaptureApp()
