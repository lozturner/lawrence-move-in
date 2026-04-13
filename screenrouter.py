"""
Lawrence: Move In — ScreenRouter v1.0.0
Watches ShareX screenshots folder. When a new screenshot lands,
pops up a tiny routing panel: add notes, pick destinations, save
structured JSON so any other bot/app can find and use the file.
"""
__version__ = "1.0.0"
import selfclean; selfclean.ensure_single("screenrouter.py")

import json, os, sys, threading, time, tkinter as tk
from tkinter import ttk
from pathlib import Path
from datetime import datetime
import watchdog.observers
import watchdog.events
import pystray
from PIL import Image, ImageDraw

SCRIPT_DIR   = Path(__file__).resolve().parent
SHAREX_DIR   = Path(os.environ.get("USERPROFILE","C:/Users/123")) / "Documents" / "ShareX" / "Screenshots"
ROUTES_FILE  = SCRIPT_DIR / "screenrouter_routes.json"
INBOX_FILE   = SCRIPT_DIR / "screenrouter_inbox.json"   # structured JSON for other bots

IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

# ── Destinations ─────────────────────────────────────────────────────────────
DESTINATIONS = {
    "niggly_machine": {
        "label": "Niggly Machine",
        "folder": str(SCRIPT_DIR / "captures"),
        "description": "Local captures folder in the suite",
    },
    "desktop": {
        "label": "Desktop",
        "folder": str(Path(os.environ.get("USERPROFILE","C:/Users/123")) / "Desktop"),
        "description": "Desktop",
    },
    "windowbot": {
        "label": "WindowBot",
        "folder": None,   # no copy — just flag for WindowBot to process
        "description": "Send to WindowBot for AI analysis",
    },
    "kidlin": {
        "label": "Kidlin AI",
        "folder": None,
        "description": "Queue for Kidlin Claude analysis",
    },
    "inbox": {
        "label": "Inbox (JSON only)",
        "folder": None,
        "description": "Just register in the JSON inbox, no copy",
    },
}

def load_inbox():
    if INBOX_FILE.exists():
        try:
            with open(INBOX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_inbox(items):
    try:
        with open(INBOX_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except:
        pass

def register_screenshot(src_path, destinations, notes, tags):
    """Write structured JSON entry so any other bot can find this file."""
    entry = {
        "id": f"sr_{int(time.time()*1000)}",
        "captured_at": datetime.now().isoformat(),
        "source_path": str(src_path),
        "filename": Path(src_path).name,
        "notes": notes,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "destinations": destinations,
        "copies": [],
        "processed_by": [],
    }
    # Copy file to folder-based destinations
    import shutil
    for dest_id in destinations:
        dest = DESTINATIONS.get(dest_id, {})
        folder = dest.get("folder")
        if folder:
            try:
                Path(folder).mkdir(parents=True, exist_ok=True)
                dst = Path(folder) / Path(src_path).name
                shutil.copy2(src_path, dst)
                entry["copies"].append(str(dst))
            except Exception as e:
                entry["copies"].append(f"ERROR: {e}")

    inbox = load_inbox()
    inbox.append(entry)
    # Keep last 500
    if len(inbox) > 500:
        inbox = inbox[-500:]
    save_inbox(inbox)
    return entry

# ── Popup ─────────────────────────────────────────────────────────────────────
class RoutePopup:
    def __init__(self, img_path: Path, on_done):
        self.img_path = img_path
        self.on_done  = on_done

        self.win = tk.Toplevel()
        self.win.title("ScreenRouter")
        self.win.configure(bg="#1a1a2e")
        self.win.attributes("-topmost", True)

        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"320x340+{sw//2 - 160}+{sh//2 - 170}")
        self.win.resizable(False, False)

        self._build()
        self.win.protocol("WM_DELETE_WINDOW", self._skip)
        self.win.focus_force()

    def _build(self):
        # Header
        hdr = tk.Frame(self.win, bg="#16213e", pady=6)
        hdr.pack(fill="x")
        tk.Label(hdr, text="New Screenshot", font=("Consolas", 9, "bold"),
                 fg="#89b4fa", bg="#16213e").pack(side="left", padx=8)
        tk.Label(hdr, text=self.img_path.name[:32], font=("Consolas", 7),
                 fg="#585b70", bg="#16213e").pack(side="right", padx=8)

        # Thumbnail
        try:
            from PIL import Image as PILImg, ImageTk
            img = PILImg.open(self.img_path)
            img.thumbnail((300, 100), PILImg.LANCZOS)
            self._thumb = ImageTk.PhotoImage(img)
            tk.Label(self.win, image=self._thumb, bg="#1a1a2e").pack(pady=(6,2))
        except:
            tk.Label(self.win, text="[screenshot]", font=("Segoe UI", 8),
                     fg="#585b70", bg="#1a1a2e").pack(pady=(6,2))

        # Notes
        tk.Label(self.win, text="Notes", font=("Segoe UI", 7, "bold"),
                 fg="#a6adc8", bg="#1a1a2e").pack(anchor="w", padx=8)
        self.notes = tk.Entry(self.win, font=("Segoe UI", 9), bg="#16213e",
                               fg="#cdd6f4", insertbackground="#89b4fa",
                               relief="flat", highlightthickness=1,
                               highlightbackground="#313244", highlightcolor="#89b4fa")
        self.notes.pack(fill="x", padx=8, pady=(2, 6))
        self.notes.focus_set()

        # Tags
        tk.Label(self.win, text="Tags (comma separated)", font=("Segoe UI", 7, "bold"),
                 fg="#a6adc8", bg="#1a1a2e").pack(anchor="w", padx=8)
        self.tags = tk.Entry(self.win, font=("Segoe UI", 9), bg="#16213e",
                              fg="#cdd6f4", insertbackground="#89b4fa",
                              relief="flat", highlightthickness=1,
                              highlightbackground="#313244", highlightcolor="#89b4fa")
        self.tags.pack(fill="x", padx=8, pady=(2, 6))

        # Destinations
        tk.Label(self.win, text="Send to", font=("Segoe UI", 7, "bold"),
                 fg="#a6adc8", bg="#1a1a2e").pack(anchor="w", padx=8)
        dest_frame = tk.Frame(self.win, bg="#1a1a2e")
        dest_frame.pack(fill="x", padx=8, pady=(2, 8))
        self._dest_vars = {}
        for did, dinfo in DESTINATIONS.items():
            var = tk.BooleanVar(value=(did == "inbox"))
            self._dest_vars[did] = var
            cb = tk.Checkbutton(dest_frame, text=dinfo["label"],
                                variable=var,
                                font=("Segoe UI", 8),
                                fg="#cdd6f4", bg="#1a1a2e",
                                selectcolor="#16213e",
                                activebackground="#1a1a2e",
                                activeforeground="#89b4fa",
                                relief="flat", bd=0)
            cb.pack(anchor="w")

        # Buttons
        btn_row = tk.Frame(self.win, bg="#1a1a2e")
        btn_row.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(btn_row, text="Send", font=("Segoe UI", 8, "bold"),
                  fg="#1a1a2e", bg="#a6e3a1", relief="flat", padx=14, pady=3,
                  cursor="hand2", command=self._send).pack(side="right", padx=(4, 0))
        tk.Button(btn_row, text="Skip", font=("Segoe UI", 8),
                  fg="#f38ba8", bg="#16213e", relief="flat", padx=10, pady=3,
                  cursor="hand2", command=self._skip).pack(side="right")

        self.notes.bind("<Return>", lambda e: self._send())
        self.notes.bind("<Escape>", lambda e: self._skip())

    def _send(self):
        notes = self.notes.get().strip()
        tags  = self.tags.get().strip()
        dests = [did for did, var in self._dest_vars.items() if var.get()]
        if not dests:
            dests = ["inbox"]
        entry = register_screenshot(self.img_path, dests, notes, tags)
        self.on_done(entry)
        self.win.destroy()

    def _skip(self):
        # Still register with no destinations so other bots know it exists
        entry = register_screenshot(self.img_path, ["inbox"], "", "")
        self.on_done(entry)
        self.win.destroy()

# ── Watcher ───────────────────────────────────────────────────────────────────
class ScreenshotHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self, queue):
        self.queue = queue
        self._seen = set()

    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() in IMG_EXTS and str(p) not in self._seen:
            self._seen.add(str(p))
            # Small delay — ShareX may still be writing the file
            time.sleep(0.8)
            if p.exists() and p.stat().st_size > 0:
                self.queue.put(p)

# ── Main App ──────────────────────────────────────────────────────────────────
class ScreenRouter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()   # invisible root — we just need mainloop

        self._queue = __import__("queue").Queue()
        self._active_popup = None

        # Watch ShareX folder (and subdirs via recursive)
        self.observer = watchdog.observers.Observer()
        handler = ScreenshotHandler(self._queue)
        SHAREX_DIR.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(handler, str(SHAREX_DIR), recursive=True)
        self.observer.start()

        self._tray()
        self.root.after(500, self._poll)

    def _poll(self):
        """Check queue on the main thread — needed to create Tk windows safely."""
        try:
            while True:
                img_path = self._queue.get_nowait()
                self._show_popup(img_path)
        except:
            pass
        self.root.after(400, self._poll)

    def _show_popup(self, img_path):
        def _done(entry):
            self._active_popup = None
            # Brief confirmation in tray tooltip
            pass
        self._active_popup = RoutePopup(img_path, _done)

    def _tray(self):
        img = Image.new("RGBA", (64, 64), (0,0,0,0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([4,4,60,60], radius=8, fill="#1a1a2e", outline="#89b4fa", width=2)
        d.rectangle([10,12,54,42], fill="#16213e", outline="#585b70", width=1)
        d.line([10,46,54,46], fill="#89b4fa", width=2)
        d.line([10,50,40,50], fill="#a6e3a1", width=2)
        d.line([10,54,30,54], fill="#a6adc8", width=1)

        def _show_inbox():
            inbox = load_inbox()
            recent = inbox[-5:]
            lines = []
            for e in reversed(recent):
                fn = Path(e["source_path"]).name[:25]
                n  = e.get("notes","")[:20] or "(no notes)"
                lines.append(f"{fn}: {n}")
            msg = "\n".join(lines) if lines else "Inbox empty"
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, f"ScreenRouter Inbox ({len(inbox)} total)", 0x40)

        menu = pystray.Menu(
            pystray.MenuItem(f"ScreenRouter v{__version__}", None, enabled=False),
            pystray.MenuItem(f"Watching: ...ShareX/Screenshots", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show last 5", _show_inbox),
            pystray.MenuItem("Open inbox JSON", lambda: os.startfile(str(INBOX_FILE)) if INBOX_FILE.exists() else None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self.tray = pystray.Icon("sr", img, f"ScreenRouter v{__version__}", menu=menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _quit(self):
        self.observer.stop()
        self.tray.stop()
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()
        self.observer.join()

if __name__ == "__main__":
    ScreenRouter().run()
