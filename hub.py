"""
hub.py  --  Lawrence: Move In  --  Floating tile launcher
Steam Deck-style HUB for the niggly_machine suite.
"""
__version__ = "1.0.0"

import json, os, sys, time, subprocess, threading
import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path

import psutil
from PIL import Image, ImageDraw, ImageFont, ImageTk
import pystray

# ── Constants ───────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PYTHONW = sys.executable.replace("python.exe", "pythonw.exe")
DETACHED = 0x00000008
HUB_CONFIG = SCRIPT_DIR / "hub_config.json"

C = dict(
    bg="#0a0a14", surface="#12122a", card="#1a1a3a", border="#2a2a50",
    text="#cdd6f4", dim="#5a5a80", lavender="#b4befe",
)

TILES = [
    ("niggly.py",     "Focus Rules",     "NM", "#a6e3a1"),
    ("tiles.py",      "Window Tiles",    "TL", "#94e2d5"),
    ("launcher.py",   "Master Launcher", "MI", "#cba6f7"),
    ("watcher.py",    "Watcher",         "WA", "#89b4fa"),
    ("voicesort.py",  "Voice Sort",      "VS", "#fab387"),
    ("kidlin.py",     "Kidlin's Law",    "KL", "#f9e2af"),
    ("scribe.py",     "Scribe",          "SC", "#89dceb"),
    ("annoyances.py", "Annoyances",      "AN", "#f38ba8"),
    ("linker.py",     "Linker v2",        "LK", "#b4befe"),
    ("mouse_pause.py","Mouse Pause",      "MP", "#f5c2e7"),
    ("nacho.py",      "NACHO",            "NA", "#cba6f7"),
    ("replay.py",     "Replay",           "RP", "#89b4fa"),
    ("winddown.py",   "Winddown",         "WD", "#a6e3a1"),
]

# ── Config ──────────────────────────────────────────────────────────────────
def load_config():
    if HUB_CONFIG.exists():
        try:
            return json.loads(HUB_CONFIG.read_text())
        except Exception:
            pass
    return {"tile_order": list(range(len(TILES))), "pos": [200, 200]}

def save_config(cfg):
    HUB_CONFIG.write_text(json.dumps(cfg, indent=2))

# ── Process management ──────────────────────────────────────────────────────
def launch_applet(script):
    path = SCRIPT_DIR / script
    if not path.exists():
        return
    subprocess.Popen([PYTHONW, str(path)], creationflags=DETACHED)

def kill_applet(script):
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = proc.info["cmdline"] or []
            if any(script in c for c in cmd):
                proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

def hard_reset(script):
    kill_applet(script)
    threading.Timer(0.3, launch_applet, args=[script]).start()

def is_running(script):
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmd = proc.info["cmdline"] or []
            if any(script in c for c in cmd):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

# ── Icon rendering ──────────────────────────────────────────────────────────
def _make_tile_icon(letters, accent, size=40):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=8, fill=accent)
    try:
        fnt = ImageFont.truetype("consola.ttf", 16)
    except OSError:
        fnt = ImageFont.load_default()
    bb = draw.textbbox((0, 0), letters, font=fnt)
    tx = (size - bb[2] + bb[0]) // 2
    ty = (size - bb[3] + bb[1]) // 2
    draw.text((tx, ty), letters, fill="#0a0a14", font=fnt)
    return img

def _make_tray_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 59, 59], radius=12, fill=C["lavender"])
    try:
        fnt = ImageFont.truetype("consola.ttf", 22)
    except OSError:
        fnt = ImageFont.load_default()
    bb = draw.textbbox((0, 0), "HB", font=fnt)
    tx = (64 - bb[2] + bb[0]) // 2
    ty = (64 - bb[3] + bb[1]) // 2
    draw.text((tx, ty), "HB", fill="#0a0a14", font=fnt)
    return img

# ── Tile widget ─────────────────────────────────────────────────────────────
class TileWidget(tk.Frame):
    def __init__(self, master, script, name, letters, accent, hub):
        super().__init__(master, bg=C["card"], width=82, height=90,
                         highlightbackground=C["border"], highlightthickness=1)
        self.pack_propagate(False)
        self.script = script
        self.name = name
        self.accent = accent
        self.hub = hub
        self.click_times = []

        pil_icon = _make_tile_icon(letters, accent)
        self._photo = ImageTk.PhotoImage(pil_icon)
        hub._photo_refs.append(self._photo)

        icon_frame = tk.Frame(self, bg=C["card"])
        icon_frame.pack(pady=(6, 0))

        self.icon_lbl = tk.Label(icon_frame, image=self._photo, bg=C["card"])
        self.icon_lbl.pack(side="left")

        self.badge = tk.Label(icon_frame, text="PY", bg=C["card"],
                              fg=C["dim"], font=("Consolas", 6))
        self.badge.pack(side="right", anchor="ne", padx=(0, 2))

        self.name_lbl = tk.Label(self, text=name, bg=C["card"], fg=C["text"],
                                 font=("Segoe UI", 8), wraplength=76)
        self.name_lbl.pack(pady=(2, 0))

        self.status_lbl = tk.Label(self, text="○", bg=C["card"], fg=C["dim"],
                                   font=("Segoe UI", 7))
        self.status_lbl.pack()

        for w in (self, self.icon_lbl, self.name_lbl, self.status_lbl,
                  self.badge, icon_frame):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-3>", self._on_right_click)

    def _on_click(self, _event=None):
        now = time.time()
        self.click_times = [t for t in self.click_times if now - t < 0.6]
        self.click_times.append(now)
        if len(self.click_times) >= 3:
            self.click_times.clear()
            hard_reset(self.script)
        else:
            launch_applet(self.script)

    def _on_enter(self, _event=None):
        for w in (self, self.icon_lbl, self.name_lbl, self.status_lbl,
                  self.badge):
            w.configure(bg=C["surface"])

    def _on_leave(self, _event=None):
        for w in (self, self.icon_lbl, self.name_lbl, self.status_lbl,
                  self.badge):
            w.configure(bg=C["card"])

    def _on_right_click(self, event):
        menu = tk.Menu(self, tearoff=0, bg=C["surface"], fg=C["text"],
                       activebackground=C["lavender"], activeforeground=C["bg"])
        menu.add_command(label="Move Up", command=lambda: self.hub._move_tile(self.script, -1))
        menu.add_command(label="Move Down", command=lambda: self.hub._move_tile(self.script, 1))
        menu.add_separator()
        menu.add_command(label="Kill", command=lambda: kill_applet(self.script))
        menu.add_command(label="Hard Reset", command=lambda: hard_reset(self.script))
        menu.tk_popup(event.x_root, event.y_root)

    def refresh(self):
        running = is_running(self.script)
        self.status_lbl.config(text="●" if running else "○",
                               fg="#a6e3a1" if running else C["dim"])

# ── HubApp ──────────────────────────────────────────────────────────────────
class HubApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("HUB")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg=C["bg"])
        self._photo_refs = []
        self.cfg = load_config()
        self.tiles = []
        self.tray_icon = None

        x, y = self.cfg.get("pos", [200, 200])
        self.root.geometry(f"290x440+{x}+{y}")

        self._build_titlebar()
        self._build_grid()
        self._build_launch_btn()
        self._refresh()
        self._start_tray()

    # ── Title bar ───────────────────────────────────────────────────────
    def _build_titlebar(self):
        bar = tk.Frame(self.root, bg=C["surface"], height=24)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        lbl = tk.Label(bar, text="  HUB", bg=C["surface"], fg=C["lavender"],
                       font=("Consolas", 10, "bold"))
        lbl.pack(side="left")

        close_btn = tk.Label(bar, text=" X ", bg=C["surface"], fg=C["dim"],
                             font=("Consolas", 10), cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda _: self._quit())

        for w in (bar, lbl):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    # ── Tile grid ───────────────────────────────────────────────────────
    def _build_grid(self):
        if hasattr(self, "grid_frame"):
            self.grid_frame.destroy()
        self.grid_frame = tk.Frame(self.root, bg=C["bg"])
        self.grid_frame.pack(fill="both", expand=True, padx=6, pady=4)
        self.tiles.clear()

        order = self.cfg.get("tile_order", list(range(len(TILES))))
        for idx, ti in enumerate(order):
            script, name, letters, accent = TILES[ti]
            tile = TileWidget(self.grid_frame, script, name, letters, accent, self)
            row, col = divmod(idx, 2)
            tile.grid(row=row, column=col, padx=4, pady=3)
            self.tiles.append(tile)

    def _move_tile(self, script, direction):
        order = self.cfg["tile_order"]
        tile_idx = None
        for i, ti in enumerate(order):
            if TILES[ti][0] == script:
                tile_idx = i
                break
        if tile_idx is None:
            return
        new_idx = tile_idx + direction
        if new_idx < 0 or new_idx >= len(order):
            return
        order[tile_idx], order[new_idx] = order[new_idx], order[tile_idx]
        save_config(self.cfg)
        self._build_grid()
        self._refresh_once()

    # ── Launch All button ───────────────────────────────────────────────
    def _build_launch_btn(self):
        btn = tk.Label(self.root, text="▶ LAUNCH ALL", bg=C["lavender"],
                       fg=C["bg"], font=("Segoe UI", 9, "bold"), cursor="hand2",
                       pady=4)
        btn.pack(fill="x", padx=6, pady=(0, 6))
        btn.bind("<Button-1>", lambda _: self._launch_all())

    def _launch_all(self):
        path = SCRIPT_DIR / "launch_all.pyw"
        if path.exists():
            subprocess.Popen([PYTHONW, str(path)], creationflags=DETACHED)

    def _kill_all(self):
        for script, *_ in TILES:
            kill_applet(script)

    # ── Refresh ─────────────────────────────────────────────────────────
    def _refresh(self):
        self._refresh_once()
        self.root.after(3000, self._refresh)

    def _refresh_once(self):
        for tile in self.tiles:
            tile.refresh()

    # ── Tray icon ───────────────────────────────────────────────────────
    def _start_tray(self):
        icon_img = _make_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda: self.root.after(0, self._show)),
            pystray.MenuItem("Launch All", lambda: self.root.after(0, self._launch_all)),
            pystray.MenuItem("Kill All", lambda: self.root.after(0, self._kill_all)),
            pystray.MenuItem("Quit", lambda: self.root.after(0, self._quit)),
        )
        self.tray_icon = pystray.Icon("hub", icon_img, "HUB", menu)
        t = threading.Thread(target=self.tray_icon.run, daemon=True)
        t.start()

    def _show(self):
        self.root.deiconify()
        self.root.lift()

    # ── Close ───────────────────────────────────────────────────────────
    def _quit(self):
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.cfg["pos"] = [x, y]
        save_config(self.cfg)
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("hub.py")
    HubApp().run()
