"""
Lawrence: Move In — Winddown v1.0.0
The missing piece: how do you FINISH?

WIND DOWN:
  1. Scans active windows, clipboard, recent files, running applets
  2. AI generates a verification checklist: "Is this actually done?"
  3. User ticks items off or AI verifies them
  4. Session saved to disk with full state

RESUME:
  5. On next launch, detects last session
  6. Offers to restore: reopen windows, restore clipboard, show notes
  7. User picks up exactly where they left off

Session data: winddown_sessions/<timestamp>/session.json
"""
__version__ = "1.0.0"

import json, os, subprocess, sys, threading, time, tkinter as tk
from datetime import datetime
from pathlib import Path

import psutil
import win32api, win32gui, win32process, win32clipboard
import pystray
from PIL import Image, ImageDraw, ImageFont, ImageTk

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
SESSIONS_DIR = SCRIPT_DIR / "winddown_sessions"
API_CFG      = SCRIPT_DIR / "kidlin_config.json"
PYTHONW      = Path(sys.executable).with_name("pythonw.exe")
RESUME_FLAG  = SCRIPT_DIR / ".winddown_resume"

# ── Palette ──────────────────────────────────────────────────────────────────
BG   = "#0a0a14"; BG2  = "#12122a"; CARD = "#1a1a3a"
CARD_HI = "#252545"; BORDER = "#2a2a50"
TEXT = "#cdd6f4"; DIM  = "#5a5a80"; LAV  = "#b4befe"
GRN  = "#a6e3a1"; PCH  = "#fab387"; MAU  = "#cba6f7"
RED  = "#f38ba8"; TEAL = "#94e2d5"; YEL  = "#f9e2af"
BLUE = "#89b4fa"

SKIP_TITLES = {"Program Manager", "Windows Input Experience", ""}
SKIP_PROCS  = {"System", "Registry", "smss.exe", "csrss.exe", "svchost.exe",
               "services.exe", "lsass.exe", "dwm.exe", "fontdrvhost.exe",
               "wininit.exe", "SearchHost.exe", "RuntimeBroker.exe"}

# ── Data collectors ──────────────────────────────────────────────────────────
def get_windows():
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
        except: exe = "unknown"
        results.append({
            "hwnd": hwnd, "exe": exe, "title": title[:120],
            "rect": list(r), "minimized": bool(win32gui.IsIconic(hwnd))
        })
    try: win32gui.EnumWindows(cb, None)
    except: pass
    return results

def get_clipboard():
    try:
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return (data or "")[:2000]
    except:
        try: win32clipboard.CloseClipboard()
        except: pass
        return ""

def get_recent_files():
    cutoff = time.time() - 3600  # last hour
    results = []
    for folder in ["Desktop", "Documents", "Downloads"]:
        p = Path(os.environ.get("USERPROFILE","")) / folder
        if not p.exists(): continue
        try:
            for f in p.iterdir():
                if f.is_file() and f.stat().st_mtime > cutoff:
                    results.append({
                        "path": str(f), "name": f.name,
                        "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                    })
        except: pass
    return sorted(results, key=lambda x: x["modified"], reverse=True)[:20]

def get_suite_status():
    """Which Lawrence applets are currently running?"""
    running = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if "python" not in (p.info["name"] or "").lower(): continue
            cmd = p.info.get("cmdline") or []
            for c in cmd:
                if c.endswith(".py") and "niggly_machine" in str(Path(c).resolve()):
                    running.append({"pid": p.info["pid"], "script": os.path.basename(c)})
        except: pass
    return running

def load_api():
    try:
        d = json.loads(API_CFG.read_text())
        return d.get("api_key",""), d.get("model","claude-sonnet-4-20250514")
    except: return "", "claude-sonnet-4-20250514"

# ── Session ──────────────────────────────────────────────────────────────────
def capture_state():
    return {
        "timestamp": datetime.now().isoformat(),
        "windows": get_windows(),
        "clipboard": get_clipboard(),
        "recent_files": get_recent_files(),
        "suite_running": get_suite_status(),
    }

def save_session(session_dir, state, checklist, notes):
    session_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "version": __version__,
        "state": state,
        "checklist": checklist,
        "notes": notes,
        "resume_actions": _build_resume_actions(state),
    }
    # Strip non-serialisable hwnd
    for w in data["state"]["windows"]:
        w.pop("hwnd", None)
    (session_dir / "session.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    # Set resume flag
    RESUME_FLAG.write_text(str(session_dir), encoding="utf-8")
    return session_dir

def _build_resume_actions(state):
    actions = []
    # Re-launch suite applets
    for s in state.get("suite_running", []):
        actions.append({"type": "launch_applet", "script": s["script"]})
    # Restore clipboard
    clip = state.get("clipboard", "")
    if clip:
        actions.append({"type": "restore_clipboard", "text": clip})
    # Reopen non-suite windows (by exe)
    seen = set()
    for w in state.get("windows", []):
        exe = w["exe"]
        if exe in seen or "python" in exe.lower(): continue
        seen.add(exe)
        actions.append({"type": "note", "text": f"Was open: {exe} — {w['title'][:60]}"})
    return actions

def load_last_session():
    if not RESUME_FLAG.exists(): return None
    sdir = Path(RESUME_FLAG.read_text().strip())
    sf = sdir / "session.json"
    if sf.exists():
        return json.loads(sf.read_text(encoding="utf-8")), sdir
    return None

# ── App ───────────────────────────────────────────────────────────────────────
class WinddownApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self._tray = None

        # Check for resume on launch
        last = load_last_session()
        if last:
            data, sdir = last
            self.root.after(500, lambda: self._show_resume(data, sdir))

        self._start_tray()
        self.root.mainloop()

    # ── Wind Down UI ──────────────────────────────────────────────────────
    def _start_winddown(self):
        self._state = capture_state()
        self._checklist = []
        self._notes = ""

        win = tk.Toplevel(self.root)
        win.title("Winddown — Wrapping Up")
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.96)
        win.configure(bg=BG)
        self._win = win

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        w, h = min(700, sw-80), min(600, sh-80)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # Header
        hdr = tk.Frame(win, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  Winddown", font=("Consolas",13,"bold"),
                 fg=MAU, bg=BG2).pack(side="left", padx=8, ipady=8)
        self._stat = tk.Label(hdr, text="scanning…", font=("Segoe UI",8),
                              fg=DIM, bg=BG2)
        self._stat.pack(side="left", padx=8)
        xb = tk.Label(hdr, text=" ✕ ", font=("Consolas",11),
                       fg=DIM, bg=BG2, cursor="hand2")
        xb.pack(side="right", padx=6)
        xb.bind("<Button-1>", lambda _: win.destroy())

        # Scroll area
        cf = tk.Frame(win, bg=BG)
        cf.pack(fill="both", expand=True, padx=10, pady=6)
        self._cv = tk.Canvas(cf, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(cf, orient="vertical", command=self._cv.yview, width=5)
        self._cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._cv.pack(fill="both", expand=True)
        self._inner = tk.Frame(self._cv, bg=BG)
        cw = self._cv.create_window((0,0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
            lambda e: self._cv.config(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>",
            lambda e: self._cv.itemconfig(cw, width=e.width))
        self._cv.bind("<Enter>",
            lambda e: self.root.bind_all("<MouseWheel>",
                lambda ev: self._cv.yview_scroll(-(ev.delta//120),"units")))
        self._cv.bind("<Leave>",
            lambda e: self.root.unbind_all("<MouseWheel>"))

        # Build sections
        self._section_state()
        self._section_checklist()
        self._section_notes()

        # Footer
        foot = tk.Frame(win, bg=BG2)
        foot.pack(fill="x")
        save_btn = tk.Label(foot, text="  💾 Save Session & Wind Down  ",
                            font=("Segoe UI",10,"bold"), fg=BG, bg=GRN,
                            padx=16, pady=8, cursor="hand2")
        save_btn.pack(pady=10)
        save_btn.bind("<Button-1>", lambda _: self._do_save())

        ai_btn = tk.Label(foot, text="🤖 AI: Check if I'm actually done",
                          font=("Segoe UI",9), fg=PCH, bg=BG2,
                          cursor="hand2", pady=4)
        ai_btn.pack(pady=(0,8))
        ai_btn.bind("<Button-1>", lambda _: self._ai_verify())

    def _section_state(self):
        """Show current state: windows, suite, clipboard, files."""
        s = self._state

        # Active windows
        self._heading("Open Windows", BLUE, f"{len(s['windows'])} visible")
        for w in s["windows"][:15]:
            mi = " (minimised)" if w.get("minimized") else ""
            self._item(f"{w['exe']}{mi}", w["title"][:60], BLUE)

        # Suite status
        suite = s["suite_running"]
        self._heading("Lawrence Suite", MAU, f"{len(suite)} running")
        for a in suite:
            self._item(a["script"], f"PID {a['pid']}", MAU)

        # Clipboard
        clip = s["clipboard"]
        if clip:
            self._heading("Clipboard", YEL, f"{len(clip)} chars")
            self._item("Current contents", clip[:100] + ("…" if len(clip)>100 else ""), YEL)

        # Recent files
        files = s["recent_files"]
        if files:
            self._heading("Files Modified (last hour)", PCH, f"{len(files)} files")
            for f in files[:8]:
                self._item(f["name"], f["modified"][:16], PCH)

    def _section_checklist(self):
        """Editable checklist — user ticks things off."""
        self._heading("Before You Go", RED, "verify these")

        # Auto-generate some checklist items
        items = []
        s = self._state
        if s["clipboard"]:
            items.append("Clipboard has content — need it saved?")
        for w in s["windows"]:
            if any(k in w["title"].lower() for k in ["unsaved","untitled","draft","new "]):
                items.append(f"Possible unsaved work: {w['exe']} — {w['title'][:50]}")
        for w in s["windows"]:
            if any(k in w["exe"].lower() for k in ["outlook","thunderbird"]):
                items.append(f"Email client open — any drafts to send?")
                break
        for w in s["windows"]:
            if any(k in w["exe"].lower() for k in ["chrome","msedge","firefox"]):
                items.append(f"Browser open — any tabs to bookmark?")
                break
        items.append("Everything saved?")
        items.append("Anything else to note before closing?")

        self._checklist = [{"text": t, "done": False} for t in items]
        self._check_vars = []

        for i, item in enumerate(self._checklist):
            f = tk.Frame(self._inner, bg=CARD, pady=4)
            f.pack(fill="x", padx=8, pady=1)

            var = tk.BooleanVar(value=False)
            self._check_vars.append(var)

            cb = tk.Checkbutton(f, variable=var, bg=CARD,
                                activebackground=CARD, selectcolor=CARD,
                                fg=GRN, font=("Segoe UI",10))
            cb.pack(side="left", padx=(8,4))

            tk.Label(f, text=item["text"], font=("Segoe UI",10),
                     fg=TEXT, bg=CARD, wraplength=500,
                     anchor="w", justify="left").pack(side="left", fill="x")

    def _section_notes(self):
        """Freeform notes field."""
        self._heading("Notes (for next time)", TEAL, "optional")
        nf = tk.Frame(self._inner, bg=CARD, padx=8, pady=8)
        nf.pack(fill="x", padx=8, pady=4)
        self._notes_txt = tk.Text(nf, bg="#12122a", fg=TEXT,
                                  insertbackground=LAV, font=("Segoe UI",10),
                                  wrap="word", height=4, relief="flat")
        self._notes_txt.pack(fill="x")
        self._notes_txt.insert("1.0", "")

    def _heading(self, title, color, badge=""):
        f = tk.Frame(self._inner, bg=BG)
        f.pack(fill="x", padx=8, pady=(12,4))
        tk.Label(f, text=title, font=("Segoe UI",10,"bold"),
                 fg=color, bg=BG).pack(side="left")
        if badge:
            tk.Label(f, text=f" {badge} ", font=("Segoe UI",7),
                     fg=BG, bg=color, padx=4).pack(side="left", padx=6)

    def _item(self, left, right, color):
        f = tk.Frame(self._inner, bg=CARD, pady=3)
        f.pack(fill="x", padx=8, pady=1)
        tk.Label(f, text=left, font=("Segoe UI",9,"bold"),
                 fg=color, bg=CARD, padx=8).pack(side="left")
        tk.Label(f, text=right, font=("Segoe UI",8),
                 fg=DIM, bg=CARD, padx=4).pack(side="left")

    # ── AI Verify ─────────────────────────────────────────────────────────
    def _ai_verify(self):
        api_key, model = load_api()
        if not api_key:
            self._stat.config(text="No API key", fg=RED)
            return
        self._stat.config(text="AI checking…", fg=PCH)

        state_summary = json.dumps({
            "windows": [{"exe":w["exe"],"title":w["title"][:50]}
                        for w in self._state["windows"][:10]],
            "clipboard_len": len(self._state["clipboard"]),
            "recent_files": [f["name"] for f in self._state["recent_files"][:8]],
            "suite": [s["script"] for s in self._state["suite_running"]],
        }, indent=1)

        def _run():
            try:
                import anthropic
                cl = anthropic.Anthropic(api_key=api_key)
                r = cl.messages.create(
                    model=model, max_tokens=300,
                    messages=[{"role":"user","content":
                        f"I'm about to wind down my computer session. Here's what's open:\n\n"
                        f"{state_summary}\n\n"
                        f"Based on what you can see, generate 3-5 specific things I should "
                        f"check or verify before I walk away. Be practical. Format as a "
                        f"simple numbered list. No preamble."}])
                text = r.content[0].text.strip()
                self.root.after(0, lambda: self._show_ai_suggestions(text))
            except Exception as e:
                self.root.after(0, lambda: self._stat.config(
                    text=f"AI error: {e}", fg=RED))

        threading.Thread(target=_run, daemon=True).start()

    def _show_ai_suggestions(self, text):
        self._stat.config(text="AI suggestions added", fg=GRN)
        self._heading("AI Recommendations", PCH, "from Claude")
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line: continue
            f = tk.Frame(self._inner, bg=CARD, pady=4)
            f.pack(fill="x", padx=8, pady=1)
            var = tk.BooleanVar(value=False)
            self._check_vars.append(var)
            cb = tk.Checkbutton(f, variable=var, bg=CARD,
                                activebackground=CARD, selectcolor=CARD,
                                fg=GRN, font=("Segoe UI",10))
            cb.pack(side="left", padx=(8,4))
            tk.Label(f, text=line, font=("Segoe UI",9),
                     fg=TEXT, bg=CARD, wraplength=500,
                     anchor="w", justify="left").pack(side="left", fill="x")
            self._checklist.append({"text": line, "done": False})

        self.root.update_idletasks()
        self._cv.yview_moveto(1.0)

    # ── Save session ──────────────────────────────────────────────────────
    def _do_save(self):
        # Update checklist with user ticks
        for i, var in enumerate(self._check_vars):
            if i < len(self._checklist):
                self._checklist[i]["done"] = var.get()

        notes = self._notes_txt.get("1.0", "end").strip()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sdir = SESSIONS_DIR / ts
        save_session(sdir, self._state, self._checklist, notes)

        # Also export a readable report
        self._export_report(sdir)

        self._stat.config(text=f"Session saved: {ts}", fg=GRN)
        self._win.after(1500, self._win.destroy)

    def _export_report(self, sdir):
        lines = [f"# Winddown Report — {datetime.now():%Y-%m-%d %H:%M}\n\n"]

        lines.append("## Open Windows\n")
        for w in self._state["windows"]:
            lines.append(f"- {w['exe']}: {w['title'][:60]}\n")

        lines.append("\n## Suite Status\n")
        for a in self._state["suite_running"]:
            lines.append(f"- {a['script']} (PID {a['pid']})\n")

        if self._state["clipboard"]:
            lines.append(f"\n## Clipboard\n```\n{self._state['clipboard'][:500]}\n```\n")

        lines.append("\n## Checklist\n")
        for item in self._checklist:
            mark = "x" if item["done"] else " "
            lines.append(f"- [{mark}] {item['text']}\n")

        notes = self._notes_txt.get("1.0","end").strip()
        if notes:
            lines.append(f"\n## Notes\n{notes}\n")

        lines.append(f"\n## Files Modified (last hour)\n")
        for f in self._state["recent_files"][:10]:
            lines.append(f"- {f['name']} ({f['modified'][:16]})\n")

        (sdir / "report.md").write_text("".join(lines), encoding="utf-8")

    # ── Resume UI ─────────────────────────────────────────────────────────
    def _show_resume(self, data, sdir):
        win = tk.Toplevel(self.root)
        win.title("Winddown — Resume Session")
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.96)
        win.configure(bg=BG)

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        w, h = min(600, sw-80), min(500, sh-80)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        hdr = tk.Frame(win, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  Welcome back", font=("Consolas",13,"bold"),
                 fg=GRN, bg=BG2).pack(side="left", padx=8, ipady=8)

        ts = data.get("state",{}).get("windows",[{}])
        when = data.get("timestamp","")[:16]
        tk.Label(hdr, text=when, font=("Consolas",9),
                 fg=DIM, bg=BG2).pack(side="right", padx=10)

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # Notes from last time
        notes = data.get("notes","")
        if notes:
            tk.Label(body, text="Your notes from last session:",
                     font=("Segoe UI",9,"bold"), fg=TEAL, bg=BG,
                     anchor="w").pack(fill="x", pady=(0,4))
            tk.Label(body, text=notes, font=("Segoe UI",11),
                     fg=TEXT, bg=CARD, wraplength=540, justify="left",
                     anchor="nw", padx=12, pady=8).pack(fill="x", pady=(0,10))

        # Resume actions
        tk.Label(body, text="Last session had:",
                 font=("Segoe UI",9,"bold"), fg=LAV, bg=BG,
                 anchor="w").pack(fill="x", pady=(0,4))

        actions = data.get("resume_actions", [])
        self._resume_vars = []
        for act in actions:
            f = tk.Frame(body, bg=CARD, pady=3)
            f.pack(fill="x", pady=1)

            var = tk.BooleanVar(value=(act["type"] == "launch_applet"))
            self._resume_vars.append((var, act))

            cb = tk.Checkbutton(f, variable=var, bg=CARD,
                                activebackground=CARD, selectcolor=CARD,
                                fg=GRN, font=("Segoe UI",9))
            cb.pack(side="left", padx=(8,4))

            if act["type"] == "launch_applet":
                txt = f"Relaunch {act['script']}"
            elif act["type"] == "restore_clipboard":
                txt = f"Restore clipboard ({len(act.get('text',''))} chars)"
            else:
                txt = act.get("text", str(act))

            tk.Label(f, text=txt, font=("Segoe UI",9),
                     fg=TEXT, bg=CARD, anchor="w").pack(side="left", fill="x")

        # Checklist status from last time
        checklist = data.get("checklist", [])
        undone = [c for c in checklist if not c.get("done")]
        if undone:
            tk.Label(body, text=f"Unchecked items from last time ({len(undone)}):",
                     font=("Segoe UI",9,"bold"), fg=YEL, bg=BG,
                     anchor="w").pack(fill="x", pady=(10,4))
            for c in undone[:5]:
                tk.Label(body, text=f"  ○  {c['text']}",
                         font=("Segoe UI",9), fg=PCH, bg=BG,
                         anchor="w").pack(fill="x")

        # Buttons
        foot = tk.Frame(win, bg=BG2)
        foot.pack(fill="x")
        bf = tk.Frame(foot, bg=BG2)
        bf.pack(pady=10)

        resume_btn = tk.Label(bf, text="  ▶ Resume Selected  ",
                              font=("Segoe UI",10,"bold"), fg=BG, bg=GRN,
                              padx=16, pady=6, cursor="hand2")
        resume_btn.pack(side="left", padx=4)
        resume_btn.bind("<Button-1>", lambda _: self._do_resume(win))

        skip_btn = tk.Label(bf, text="  Skip  ",
                            font=("Segoe UI",10), fg=DIM, bg=CARD,
                            padx=16, pady=6, cursor="hand2")
        skip_btn.pack(side="left", padx=4)
        skip_btn.bind("<Button-1>", lambda _: (self._clear_resume(), win.destroy()))

    def _do_resume(self, win):
        for var, act in self._resume_vars:
            if not var.get(): continue

            if act["type"] == "launch_applet":
                script = SCRIPT_DIR / act["script"]
                if script.exists():
                    subprocess.Popen([str(PYTHONW), str(script)],
                                     creationflags=0x8, cwd=str(SCRIPT_DIR))

            elif act["type"] == "restore_clipboard":
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(act.get("text",""))
                except: pass

        self._clear_resume()
        win.destroy()

    def _clear_resume(self):
        if RESUME_FLAG.exists():
            RESUME_FLAG.unlink()

    # ── Tray ──────────────────────────────────────────────────────────────
    def _start_tray(self):
        img = Image.new("RGBA",(64,64),(0,0,0,0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([4,4,59,59], radius=12, fill=(166,227,161))
        try: fnt = ImageFont.truetype("consola.ttf",20)
        except: fnt = ImageFont.load_default()
        bb = d.textbbox((0,0),"WD",font=fnt)
        d.text(((64-(bb[2]-bb[0]))//2,(64-(bb[3]-bb[1]))//2),
               "WD", fill="#0a0a14", font=fnt)

        menu = pystray.Menu(
            pystray.MenuItem("Wind Down",
                lambda icon, item: self.root.after(0, self._start_winddown)),
            pystray.MenuItem("Browse Sessions",
                lambda icon, item: self.root.after(0, self._browse)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",
                lambda icon, item: self._quit(icon)),
        )
        self._tray = pystray.Icon("winddown", img, "Winddown", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _browse(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        sessions = sorted(
            [s for s in SESSIONS_DIR.iterdir() if (s/"session.json").exists()],
            reverse=True)

        dlg = tk.Toplevel(self.root)
        dlg.title("Winddown Sessions")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=BG)
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"350x400+{(sw-350)//2}+{(sh-400)//2}")

        tk.Label(dlg, text="  Winddown Sessions", bg=BG2, fg=GRN,
                 font=("Consolas",11,"bold"), anchor="w").pack(fill="x", ipady=8)

        if not sessions:
            tk.Label(dlg, text="No sessions yet.",
                     font=("Segoe UI",10), fg=DIM, bg=BG).pack(expand=True)
        else:
            for s in sessions[:15]:
                try:
                    d = json.loads((s/"session.json").read_text(encoding="utf-8"))
                    dt = d.get("timestamp","")[:16]
                    nw = len(d.get("state",{}).get("windows",[]))
                    label = f"{dt}  —  {nw} windows"
                except: label = s.name

                row = tk.Label(dlg, text=label, font=("Segoe UI",9),
                               fg=TEXT, bg=CARD, anchor="w", padx=10, pady=6,
                               cursor="hand2")
                row.pack(fill="x", padx=8, pady=1)
                row.bind("<Enter>", lambda e, w=row: w.config(bg=CARD_HI))
                row.bind("<Leave>", lambda e, w=row: w.config(bg=CARD))
                row.bind("<Button-1>",
                    lambda e, sd=s: (dlg.destroy(), self._show_resume(
                        json.loads((sd/"session.json").read_text(encoding="utf-8")), sd)))

        cb = tk.Label(dlg, text="Close", bg=BG2, fg=DIM,
                      font=("Segoe UI",8), cursor="hand2", pady=4)
        cb.pack(fill="x")
        cb.bind("<Button-1>", lambda _: dlg.destroy())

    def _quit(self, icon=None):
        if icon: icon.stop()
        try: self.root.destroy()
        except: pass


if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("winddown.py")
    WinddownApp()
