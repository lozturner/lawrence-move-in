"""
Lawrence: Move In — ScreenRouter v2.0.0
Watches ShareX folder. New screenshot → clean popup asking one question.
Thumbnail click → fullscreen viewer, click/ESC to return.
Then offers routing destinations with email as default.
State + queue persisted to JSON so nothing is lost.
"""
__version__ = "2.0.0"
import selfclean; selfclean.ensure_single("screenrouter.py")

import json, os, queue, shutil, sys, threading, time, urllib.parse
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime
from pathlib import Path

import watchdog.observers, watchdog.events
import pystray
from PIL import Image as PILImage, ImageTk

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
USERPROFILE = Path(os.environ.get("USERPROFILE", "C:/Users/123"))
SHAREX_DIR  = USERPROFILE / "Documents" / "ShareX" / "Screenshots"
STATE_FILE  = SCRIPT_DIR / "screenrouter_state.json"   # persistent queue + prefs
INBOX_FILE  = SCRIPT_DIR / "screenrouter_inbox.json"   # structured records for bots
THUMB_CACHE = SCRIPT_DIR / ".sr_thumbs"                # thumbnail cache dir
IMG_EXTS    = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

# ── Colours ───────────────────────────────────────────────────────────────────
BG       = "#1a1a2e"
BG2      = "#16213e"
BG3      = "#0f3460"
FG       = "#cdd6f4"
FG_DIM   = "#585b70"
BLUE     = "#89b4fa"
GREEN    = "#a6e3a1"
YELLOW   = "#f9e2af"
RED      = "#f38ba8"
PURPLE   = "#cba6f7"
LOCKED   = "#45475a"

# ── Suite apps (named separately) ─────────────────────────────────────────────
SUITE_APPS = {
    "suite_windowbot": {
        "label": "Suite · WindowBot",
        "script": "windowbot.py",
        "desc":   "Send to WindowBot for AI window commands",
    },
    "suite_kidlin": {
        "label": "Suite · Kidlin AI",
        "script": "kidlin.py",
        "desc":   "Queue for Kidlin Claude analysis",
    },
    "suite_captures": {
        "label": "Suite · Captures",
        "folder": str(SCRIPT_DIR / "captures"),
        "desc":   "Copy to Niggly Machine captures/",
    },
    "suite_niggly": {
        "label": "Suite · Niggly",
        "script": "niggly.py",
        "desc":   "Send to Niggly panel",
    },
}

# ── State persistence ──────────────────────────────────────────────────────────
def _load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "pending_queue": [],      # screenshot paths waiting for popup
        "last_destinations": ["email"],  # remember last selection
        "prefs": {},
    }

def _save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except: pass

def _load_inbox():
    if INBOX_FILE.exists():
        try:
            with open(INBOX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return []

def _save_inbox(items):
    try:
        with open(INBOX_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except: pass

# ── Routing ────────────────────────────────────────────────────────────────────
def _route(src: Path, notes: str, tags_str: str, destinations: list):
    """Copy files, open email, write inbox JSON. Returns the entry dict."""
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    ts   = datetime.now().isoformat()

    entry = {
        "id":           f"sr_{int(time.time()*1000)}",
        "captured_at":  ts,
        "source_path":  str(src),
        "filename":     src.name,
        "notes":        notes,
        "tags":         tags,
        "destinations": destinations,
        "copies":       [],
        "breadcrumbs":  {},
    }

    for dest in destinations:
        # ── Email ──
        if dest == "email":
            _send_mailto(src, notes, tags, entry["id"])

        # ── Desktop ──
        elif dest == "desktop":
            dst = USERPROFILE / "Desktop" / src.name
            try: shutil.copy2(src, dst); entry["copies"].append(str(dst))
            except Exception as e: entry["copies"].append(f"ERROR desktop: {e}")

        # ── Suite apps ──
        elif dest in SUITE_APPS:
            info = SUITE_APPS[dest]
            if "folder" in info:
                folder = Path(info["folder"])
                folder.mkdir(parents=True, exist_ok=True)
                dst = folder / src.name
                try: shutil.copy2(src, dst); entry["copies"].append(str(dst))
                except Exception as e: entry["copies"].append(f"ERROR {dest}: {e}")
            # flag it in entry so the suite app can pick it up
            entry["breadcrumbs"][dest] = {"status": "queued", "ts": ts}

    # Write to inbox
    inbox = _load_inbox()
    inbox.append(entry)
    if len(inbox) > 1000:
        inbox = inbox[-1000:]
    _save_inbox(inbox)
    return entry

def _send_mailto(src: Path, notes: str, tags: list, entry_id: str):
    """Open default email client with a well-structured screenshot note."""
    tag_str  = " ".join(f"#{t}" for t in tags) if tags else "#screenshot"
    emoji    = "📸"
    short    = notes[:60] if notes else "new screenshot"
    date_str = datetime.now().strftime("%Y-%m-%d")

    subject = f"{emoji} {short} | {tag_str} | {date_str}"

    body_lines = [
        f"{emoji} Screenshot captured: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Notes: {notes or '(none)'}",
        f"Tags: {tag_str}",
        f"File: {src}",
        "",
        "─" * 40,
        "🤖 METADATA — for AI/bots",
        "─" * 40,
        json.dumps({
            "type":      "screenshot_note",
            "source":    "screenrouter",
            "id":        entry_id,
            "file":      str(src),
            "notes":     notes,
            "tags":      tags,
            "timestamp": datetime.now().isoformat(),
        }, indent=2),
    ]
    body = "\n".join(body_lines)

    uri = "mailto:?subject=" + urllib.parse.quote(subject) + \
          "&body="            + urllib.parse.quote(body)
    try:
        os.startfile(uri)
    except Exception:
        pass

# ── Thumbnail helpers ──────────────────────────────────────────────────────────
def _make_thumb(src: Path, w=300, h=130):
    """Return a cached PIL thumbnail image."""
    THUMB_CACHE.mkdir(parents=True, exist_ok=True)
    cache = THUMB_CACHE / f"{src.stem}_{w}x{h}.png"
    if cache.exists():
        try:
            return PILImage.open(cache).copy()
        except: pass
    try:
        img = PILImage.open(src)
        img.thumbnail((w, h), PILImage.LANCZOS)
        img.save(cache, "PNG")
        return img
    except:
        return None

# ── Fullscreen viewer ──────────────────────────────────────────────────────────
class FullscreenViewer:
    def __init__(self, src: Path, return_to_win):
        self._src         = src
        self._return_to   = return_to_win   # hwnd or Tk window to refocus after close
        self._win         = tk.Toplevel()
        self._win.configure(bg="black")
        self._win.attributes("-topmost", True)
        self._win.attributes("-fullscreen", True)
        self._win.focus_force()

        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()

        try:
            img = PILImage.open(src)
            img.thumbnail((sw, sh - 40), PILImage.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            lbl = tk.Label(self._win, image=self._photo, bg="black", cursor="hand2")
            lbl.pack(expand=True)
        except:
            tk.Label(self._win, text=str(src), fg="white", bg="black",
                     font=("Segoe UI", 12)).pack(expand=True)

        hint = tk.Label(self._win, text="Click or press ESC to close",
                        fg="#585b70", bg="black", font=("Segoe UI", 8))
        hint.pack(pady=4)

        self._win.bind("<Button-1>", lambda e: self._close())
        self._win.bind("<Escape>",   lambda e: self._close())

    def _close(self):
        self._win.destroy()
        try:
            self._return_to.focus_force()
            self._return_to.lift()
        except: pass

# ── Main popup ─────────────────────────────────────────────────────────────────
class RoutePopup:
    """Two-panel popup. Panel 1: thumbnail + question. Panel 2: destinations."""

    def __init__(self, src: Path, on_done, last_dests: list):
        self.src        = src
        self.on_done    = on_done
        self.last_dests = last_dests

        self.win = tk.Toplevel()
        self.win.title("ScreenRouter")
        self.win.configure(bg=BG)
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)

        # Position: centre of screen
        self.win.update_idletasks()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"360x320+{sw//2-180}+{sh//2-160}")

        # Pre-load thumbnail
        self._thumb_pil   = _make_thumb(src, 320, 140)
        self._thumb_photo = None
        self._thumb_small = None

        self._dest_vars   = {}
        self._panel1      = tk.Frame(self.win, bg=BG)
        self._panel2      = tk.Frame(self.win, bg=BG)

        self._build_panel1()
        self._build_panel2()
        self._show_panel1()

        self.win.protocol("WM_DELETE_WINDOW", self._skip)

    # ── Panel 1: thumbnail + question ─────────────────────────────────────────
    def _build_panel1(self):
        f = self._panel1

        # Header
        hdr = tk.Frame(f, bg=BG2, pady=5)
        hdr.pack(fill="x")
        tk.Label(hdr, text="New screenshot", font=("Segoe UI", 9, "bold"),
                 fg=BLUE, bg=BG2).pack(side="left", padx=10)
        tk.Label(hdr, text=self.src.name[:28], font=("Consolas", 7),
                 fg=FG_DIM, bg=BG2).pack(side="right", padx=10)

        # Thumbnail — click for fullscreen
        if self._thumb_pil:
            self._thumb_photo = ImageTk.PhotoImage(self._thumb_pil)
            lbl = tk.Label(f, image=self._thumb_photo, bg=BG, cursor="hand2",
                           relief="flat")
            lbl.pack(pady=(8, 4), padx=8)
            lbl.bind("<Button-1>", lambda e: FullscreenViewer(self.src, self.win))
            tk.Label(f, text="click image to view full screen",
                     font=("Segoe UI", 7), fg=FG_DIM, bg=BG).pack()
        else:
            tk.Label(f, text="[image preview unavailable]",
                     font=("Segoe UI", 8), fg=FG_DIM, bg=BG).pack(pady=20)

        # Question
        tk.Label(f, text="What do you want to say about this image?",
                 font=("Segoe UI", 9), fg=FG, bg=BG,
                 wraplength=320).pack(pady=(10, 4), padx=10, anchor="w")

        self._notes_var = tk.StringVar()
        entry = tk.Entry(f, textvariable=self._notes_var,
                         font=("Segoe UI", 10), bg=BG2, fg=FG,
                         insertbackground=BLUE, relief="flat",
                         highlightthickness=2,
                         highlightbackground=BG3,
                         highlightcolor=BLUE)
        entry.pack(fill="x", padx=10, pady=(0, 10), ipady=6)
        entry.bind("<Return>", lambda e: self._to_panel2())
        entry.bind("<Escape>", lambda e: self._skip())
        entry.focus_set()

        tk.Button(f, text="Next  →", font=("Segoe UI", 9, "bold"),
                  fg=BG, bg=GREEN, relief="flat", padx=16, pady=4,
                  cursor="hand2",
                  command=self._to_panel2).pack(side="right", padx=10, pady=(0, 10))

    # ── Panel 2: destinations ──────────────────────────────────────────────────
    def _build_panel2(self):
        f = self._panel2

        # Compact header with mini-thumb + note preview
        hdr = tk.Frame(f, bg=BG2, pady=5)
        hdr.pack(fill="x")
        if self._thumb_pil:
            mini = self._thumb_pil.copy(); mini.thumbnail((48, 28), PILImage.LANCZOS)
            self._thumb_small = ImageTk.PhotoImage(mini)
            tk.Label(hdr, image=self._thumb_small, bg=BG2).pack(side="left", padx=6)
        self._note_preview = tk.Label(hdr, text="", font=("Segoe UI", 8, "italic"),
                                      fg=FG_DIM, bg=BG2, wraplength=240, anchor="w",
                                      justify="left")
        self._note_preview.pack(side="left", padx=4)

        # Scrollable content
        canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=0, pady=0)
        inner = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        def _row(parent, key, label, color, locked=False, default=False):
            r = tk.Frame(parent, bg=BG, pady=1)
            r.pack(fill="x", padx=12, pady=1)
            if locked:
                tk.Label(r, text="🔒", font=("Segoe UI", 9), fg=LOCKED, bg=BG
                         ).pack(side="left", padx=(0, 4))
                tk.Label(r, text=label, font=("Segoe UI", 9), fg=LOCKED, bg=BG
                         ).pack(side="left")
            else:
                var = tk.BooleanVar(value=(key in self.last_dests) or default)
                self._dest_vars[key] = var
                cb = tk.Checkbutton(r, text=label, variable=var,
                                    font=("Segoe UI", 9, "bold" if default else "normal"),
                                    fg=color, bg=BG, selectcolor=BG2,
                                    activebackground=BG, activeforeground=color,
                                    relief="flat", bd=0)
                cb.pack(side="left")

        def _section(parent, title):
            tk.Label(parent, text=title, font=("Segoe UI", 7, "bold"),
                     fg=FG_DIM, bg=BG).pack(anchor="w", padx=12, pady=(8, 2))

        # — Standard destinations —
        _section(inner, "SEND TO")
        _row(inner, "email",   "📧  Email  (default — always captures a record)", GREEN,  default=True)
        _row(inner, "desktop", "🖥  Desktop",                                     FG)
        _row(inner, None,      "📱  Telegram",                                    LOCKED, locked=True)
        _row(inner, None,      "📂  Send to Application",                         LOCKED, locked=True)

        # — Lawrence Suite —
        _section(inner, "LAWRENCE SUITE")
        for key, info in SUITE_APPS.items():
            _row(inner, key, info["label"], YELLOW)

        # Resize canvas after build
        inner.update_idletasks()
        canvas.configure(height=min(inner.winfo_reqheight(), 180))

        # Buttons
        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(fill="x", padx=10, pady=8)
        tk.Button(btn_row, text="← Back", font=("Segoe UI", 8),
                  fg=FG_DIM, bg=BG2, relief="flat", padx=10, pady=3,
                  cursor="hand2", command=self._to_panel1).pack(side="left")
        tk.Button(btn_row, text="Skip", font=("Segoe UI", 8),
                  fg=RED, bg=BG2, relief="flat", padx=10, pady=3,
                  cursor="hand2", command=self._skip).pack(side="left", padx=6)
        tk.Button(btn_row, text="Send  ✓", font=("Segoe UI", 9, "bold"),
                  fg=BG, bg=GREEN, relief="flat", padx=16, pady=4,
                  cursor="hand2", command=self._send).pack(side="right")

    # ── Navigation ─────────────────────────────────────────────────────────────
    def _show_panel1(self):
        self._panel2.pack_forget()
        self._panel1.pack(fill="both", expand=True)
        self.win.geometry("360x320")

    def _to_panel2(self):
        note = self._notes_var.get().strip()
        preview = (note[:40] + "…") if len(note) > 40 else note or "(no notes)"
        self._note_preview.config(text=preview)
        self._panel1.pack_forget()
        self._panel2.pack(fill="both", expand=True)
        self.win.geometry("360x360")

    def _to_panel1(self):
        self._panel2.pack_forget()
        self._panel1.pack(fill="both", expand=True)
        self.win.geometry("360x320")

    # ── Actions ────────────────────────────────────────────────────────────────
    def _send(self):
        notes = self._notes_var.get().strip()
        dests = [k for k, v in self._dest_vars.items() if v.get()]
        if not dests:
            dests = ["email"]
        entry = _route(self.src, notes, "", dests)
        self.on_done(entry, dests)
        self.win.destroy()

    def _skip(self):
        entry = _route(self.src, "", "", ["inbox"])
        self.on_done(entry, [])
        self.win.destroy()

# ── File watcher ───────────────────────────────────────────────────────────────
class _Handler(watchdog.events.FileSystemEventHandler):
    def __init__(self, q):
        self._q    = q
        self._seen = set()

    def on_created(self, event):
        if event.is_directory: return
        p = Path(event.src_path)
        if p.suffix.lower() not in IMG_EXTS: return
        key = str(p)
        if key in self._seen: return
        self._seen.add(key)
        # Wait for ShareX to finish writing
        threading.Thread(target=self._wait_and_queue, args=(p,), daemon=True).start()

    def _wait_and_queue(self, p):
        for _ in range(10):
            time.sleep(0.5)
            try:
                if p.exists() and p.stat().st_size > 500:
                    self._q.put(p)
                    return
            except: pass

# ── App ────────────────────────────────────────────────────────────────────────
class ScreenRouter:
    def __init__(self):
        self.root    = tk.Tk()
        self.root.withdraw()
        self._q      = queue.Queue()
        self._busy   = False   # one popup at a time
        self._state  = _load_state()

        # Restore any pending queue items from last run
        for path_str in self._state.get("pending_queue", []):
            p = Path(path_str)
            if p.exists():
                self._q.put(p)
        self._state["pending_queue"] = []
        _save_state(self._state)

        # Start watcher
        SHAREX_DIR.mkdir(parents=True, exist_ok=True)
        self._observer = watchdog.observers.Observer()
        self._observer.schedule(_Handler(self._q), str(SHAREX_DIR), recursive=True)
        self._observer.start()

        self._tray()
        self.root.after(600, self._poll)

    def _poll(self):
        if not self._busy:
            try:
                img_path = self._q.get_nowait()
                self._busy = True
                RoutePopup(
                    img_path,
                    on_done=self._popup_done,
                    last_dests=self._state.get("last_destinations", ["email"]),
                )
            except queue.Empty:
                pass
        self.root.after(400, self._poll)

    def _popup_done(self, entry, dests):
        if dests:
            self._state["last_destinations"] = dests
        # Flush any pending paths to state so next run picks them up
        pending = []
        while True:
            try: pending.append(str(self._q.get_nowait()))
            except queue.Empty: break
        self._state["pending_queue"] = pending
        _save_state(self._state)
        self._busy = False

    def _tray(self):
        img = PILImage.new("RGBA", (64, 64), (0,0,0,0))
        d = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).ImageDraw.Draw(img)
        d.rounded_rectangle([4,4,60,60], radius=8, fill=BG2, outline=BLUE, width=2)
        # camera icon
        d.rectangle([12,18,52,46], fill=BG3, outline=BLUE, width=1)
        d.ellipse([24,22,40,38], fill=BLUE)
        d.rectangle([44,14,56,22], fill=BLUE)

        menu = pystray.Menu(
            pystray.MenuItem(f"ScreenRouter v{__version__}", None, enabled=False),
            pystray.MenuItem("Watching ShareX folder", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Last 5 in inbox", self._show_inbox),
            pystray.MenuItem("Open inbox JSON",
                lambda: os.startfile(str(INBOX_FILE)) if INBOX_FILE.exists() else None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self._tray_icon = pystray.Icon("sr", img, f"ScreenRouter v{__version__}", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _show_inbox(self, icon=None, item=None):
        inbox = _load_inbox()
        if not inbox:
            msg = "Inbox is empty."
        else:
            lines = []
            for e in reversed(inbox[-5:]):
                fn   = Path(e["source_path"]).name[:28]
                note = (e.get("notes") or "(no notes)")[:35]
                dsts = ", ".join(e.get("destinations", []))
                lines.append(f"{fn}\n  → {note}\n  [{dsts}]")
            msg = f"Last {min(5,len(inbox))} of {len(inbox)} total:\n\n" + "\n\n".join(lines)
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "ScreenRouter Inbox", 0x40)

    def _quit(self, icon=None, item=None):
        # Save pending queue before exit
        pending = []
        while True:
            try: pending.append(str(self._q.get_nowait()))
            except queue.Empty: break
        self._state["pending_queue"] = pending
        _save_state(self._state)
        self._observer.stop()
        self._tray_icon.stop()
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()
        self._observer.join()

if __name__ == "__main__":
    ScreenRouter().run()
