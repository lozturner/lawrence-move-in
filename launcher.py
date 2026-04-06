"""Lawrence: Move In — Master Launcher v2.0.0"""
__version__ = "2.0.0"

import json, os, subprocess, sys, threading, time, tkinter as tk
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageTk
import pystray

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "launcher_config.json"
PYTHONW = sys.executable.replace("python.exe", "pythonw.exe")
if not Path(PYTHONW).exists():
    PYTHONW = sys.executable
MY_PID = os.getpid()
DETACHED = 0x00000008

C = dict(
    bg="#0a0a16", surface="#12122a", card="#1a1a3a", border="#2a2a50",
    text="#cdd6f4", dim="#5a5a80", blue="#89b4fa", green="#a6e3a1",
    red="#f38ba8", peach="#fab387", mauve="#cba6f7", teal="#94e2d5",
    yellow="#f9e2af", pink="#f5c2e7", sky="#89dceb", white="#ffffff",
)

APPLETS = [
    dict(id="niggly", name="Focus Rules", subtitle="IF/THEN window hiding",
         icon_text="NM", colour=C["green"], script="niggly.py"),
    dict(id="tiles", name="Window Tiles", subtitle="Sidebar + Desktop Canvas",
         icon_text="TL", colour=C["blue"], script="tiles.py"),
    dict(id="canvas", name="Desktop Canvas", subtitle="Full-screen overlay",
         icon_text="DC", colour=C["teal"], script="_open_canvas.py"),
]

SUITE_SCRIPTS = ["niggly.py", "tiles.py", "launcher.py", "_open_canvas.py",
                 "launch_all.pyw", "kill_all.py"]

def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _font(name="segoeuib.ttf", size=14):
    try: return ImageFont.truetype(name, size)
    except Exception:
        try: return ImageFont.truetype("arial.ttf", size)
        except Exception: return ImageFont.load_default()

def _load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"launches": {}, "total_launches": 0, "xp": 0, "level": 1}

def _save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def _is_running(script_name):
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if "python" not in (proc.info.get("name") or "").lower():
                    continue
                cmdline = proc.info.get("cmdline") or []
                if any(script_name in str(c) for c in cmdline):
                    if proc.info["pid"] != MY_PID:
                        return True
            except Exception:
                pass
    except ImportError:
        pass
    return False

def _kill_old_suite():
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            if proc.info["pid"] == MY_PID:
                continue
            try:
                if "python" not in (proc.info.get("name") or "").lower():
                    continue
                cmd_str = " ".join(str(c) for c in (proc.info.get("cmdline") or []))
                for s in SUITE_SCRIPTS:
                    if s in cmd_str:
                        proc.terminate()
                        break
            except Exception:
                pass
    except ImportError:
        pass

def render_orb(text, colour, size=44, active=False):
    pad = 10
    full = size + pad * 2
    img = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = full // 2, full // 2, size // 2
    rgb = _hex(colour)
    if active:
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=rgb)
        tcol = (255, 255, 255)
    else:
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=tuple(c//3 for c in rgb))
        d.ellipse([cx-r, cy-r, cx+r, cy+r], outline=rgb, width=2)
        tcol = rgb
    d.text((cx, cy), text, fill=tcol, font=_font(size=size//3), anchor="mm")
    return img

def render_xp_ring(xp, max_xp, level, size=90):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = size//2, size//2, size//2 - 5
    d.ellipse([cx-r, cy-r, cx+r, cy+r], outline=_hex(C["border"]), width=3)
    progress = min(xp / max(max_xp, 1), 1.0)
    if progress > 0:
        d.arc([cx-r, cy-r, cx+r, cy+r], -90, -90 + int(360*progress),
              fill=_hex(C["mauve"]), width=4)
    d.text((cx, cy-7), str(level), fill=_hex(C["mauve"]),
           font=_font(size=20), anchor="mm")
    sm = _font("segoeui.ttf", 8)
    d.text((cx, cy+10), "LEVEL", fill=_hex(C["dim"]), font=sm, anchor="mm")
    d.text((cx, cy+21), f"{xp}/{max_xp} XP", fill=_hex(C["dim"]),
           font=sm, anchor="mm")
    return img

def render_stat_ring(value, label, colour, size=50):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = size//2, size//2, size//2 - 3
    d.ellipse([cx-r, cy-r, cx+r, cy+r], outline=_hex(colour), width=2)
    d.text((cx, cy-5), str(value), fill=_hex(colour),
           font=_font(size=13), anchor="mm")
    d.text((cx, cy+9), label, fill=_hex(C["dim"]),
           font=_font("segoeui.ttf", 7), anchor="mm")
    return img

def _tray_icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, 60, 60], fill=_hex(C["mauve"]))
    d.text((32, 32), "MI", fill=(10, 10, 22), font=_font(size=20), anchor="mm")
    return img


class Launcher:
    def __init__(self):
        self.root = None
        self.config = _load_config()
        self._photo_refs = []
        self._alive = True
        self._procs = {}
        self._clock_id = None
        self._config_lock = threading.Lock()
        self._show_lock = threading.Lock()
        self._launch_locks = {a["id"]: threading.Lock() for a in APPLETS}
        self._rebuilding = False
        self._status = {a["id"]: None for a in APPLETS}
        self._dot_labels = {}
        self._btn_labels = {}
        self._stats_frame = None

    def show(self):
        with self._show_lock:
            if self.root:
                try:
                    if self.root.winfo_exists():
                        self.root.lift()
                        return
                except Exception:
                    pass
            self.root = tk.Tk()
            self.root.title(f"Lawrence: Move In v{__version__}")
            self.root.configure(bg=C["bg"])
            self.root.geometry("540x580")
            self.root.minsize(460, 480)
            self.root.protocol("WM_DELETE_WINDOW", self._close)
            self._build()
            self.root.after(100, self._apply_dark_titlebar)
            self._start_poll()
        self.root.mainloop()

    def _apply_dark_titlebar(self):
        try:
            import ctypes
            self.root.update_idletasks()
            hwnd = self.root.winfo_id()
            parent = ctypes.windll.user32.GetAncestor(hwnd, 2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                parent or hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
        except Exception:
            pass

    def _build(self):
        self._photo_refs.clear()
        hdr = tk.Frame(self.root, bg=C["bg"])
        hdr.pack(fill="x", padx=20, pady=(14, 0))
        tk.Label(hdr, text=f"Lawrence: Move In v{__version__}",
                 font=("Segoe UI", 16, "bold"), fg=C["mauve"],
                 bg=C["bg"]).pack(side="left")
        self._clock_lbl = tk.Label(hdr, font=("Segoe UI", 9),
                                   fg=C["dim"], bg=C["bg"])
        self._clock_lbl.pack(side="right")
        self._tick_clock()
        tk.Label(self.root, text="Portable suite to fix your Windows niggles",
                 font=("Segoe UI", 9), fg=C["dim"], bg=C["bg"]
                 ).pack(anchor="w", padx=20, pady=(1, 10))
        self._stats_frame = tk.Frame(self.root, bg=C["bg"])
        self._stats_frame.pack(pady=(0, 8))
        self._render_stats()
        tk.Label(self.root, text="APPLETS", font=("Segoe UI", 8, "bold"),
                 fg=C["dim"], bg=C["bg"]).pack(anchor="w", padx=20, pady=(4, 4))
        cards = tk.Frame(self.root, bg=C["bg"])
        cards.pack(fill="x", padx=14)
        for a in APPLETS:
            self._draw_card(cards, a)
        bf = tk.Frame(self.root, bg=C["bg"])
        bf.pack(pady=(14, 8))
        self._make_btn(bf, "  Launch All  ", C["green"], C["teal"],
                       lambda: self._launch_all())
        self._make_btn(bf, "  Stop All  ", C["red"], C["peach"],
                       lambda: self._stop_all())
        tk.Label(self.root, text="+10 XP per launch",
                 font=("Segoe UI", 7), fg=C["dim"], bg=C["bg"]
                 ).pack(side="bottom", pady=5)

    def _make_btn(self, parent, text, bg_col, hover_col, cmd):
        b = tk.Label(parent, text=text, font=("Segoe UI", 10, "bold"),
                     fg=C["bg"], bg=bg_col, padx=28, pady=8, cursor="hand2")
        b.pack(side="left", padx=10)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.config(bg=hover_col))
        b.bind("<Leave>", lambda e: b.config(bg=bg_col))

    def _render_stats(self):
        for w in self._stats_frame.winfo_children():
            w.destroy()
        xp = self.config.get("xp", 0)
        level = self.config.get("level", 1)
        max_xp = level * 50
        total = self.config.get("total_launches", 0)
        active = sum(1 for a in APPLETS if self._status.get(a["id"]))
        xp_ph = ImageTk.PhotoImage(render_xp_ring(xp, max_xp, level, 90))
        self._photo_refs.append(xp_ph)
        tk.Label(self._stats_frame, image=xp_ph, bg=C["bg"]).pack(
            side="left", padx=(8, 10))
        for val, lbl, col in [(total, "LAUNCHES", C["peach"]),
                               (active, "ACTIVE", C["green"]),
                               (len(APPLETS), "APPLETS", C["blue"])]:
            sp = ImageTk.PhotoImage(render_stat_ring(val, lbl, col, 50))
            self._photo_refs.append(sp)
            tk.Label(self._stats_frame, image=sp, bg=C["bg"]).pack(
                side="left", padx=5)

    def _draw_card(self, parent, applet):
        active = self._status.get(applet["id"])
        accent = applet["colour"]
        outer = tk.Frame(parent, bg=accent)
        outer.pack(fill="x", padx=6, pady=3)
        card = tk.Frame(outer, bg=C["card"])
        card.pack(fill="x", padx=(3, 0))
        orb_ph = ImageTk.PhotoImage(
            render_orb(applet["icon_text"], accent, 44, active=bool(active)))
        self._photo_refs.append(orb_ph)
        orb = tk.Label(card, image=orb_ph, bg=C["card"], cursor="hand2")
        orb.pack(side="left", padx=(8, 6), pady=6)
        orb.bind("<Button-1>", lambda e, a=applet: self._launch_applet(a))
        info = tk.Frame(card, bg=C["card"])
        info.pack(side="left", fill="both", expand=True, pady=6)
        tk.Label(info, text=applet["name"], font=("Segoe UI", 11, "bold"),
                 fg=accent, bg=C["card"]).pack(anchor="w")
        tk.Label(info, text=applet["subtitle"], font=("Segoe UI", 8),
                 fg=C["dim"], bg=C["card"]).pack(anchor="w")
        launches = self.config.get("launches", {}).get(applet["id"], 0)
        tk.Label(info, text=f"{launches} launches", font=("Segoe UI", 7),
                 fg=C["dim"], bg=C["card"]).pack(anchor="w")
        right = tk.Frame(card, bg=C["card"])
        right.pack(side="right", padx=10, pady=6)
        if active is None:
            dot_col, dot_text = C["dim"], "\u25cb Unknown"
        elif active:
            dot_col, dot_text = C["green"], "\u25cf Running"
        else:
            dot_col, dot_text = C["dim"], "\u25cb Stopped"
        dot_lbl = tk.Label(right, text=dot_text, font=("Segoe UI", 7),
                           fg=dot_col, bg=C["card"])
        dot_lbl.pack(pady=(0, 3))
        self._dot_labels[applet["id"]] = dot_lbl
        if active:
            btn_text, btn_fg, btn_bg = "Running", C["green"], C["card"]
        else:
            btn_text, btn_fg, btn_bg = "Launch", C["bg"], accent
        btn = tk.Label(right, text=btn_text, font=("Segoe UI", 8, "bold"),
                       fg=btn_fg, bg=btn_bg, padx=12, pady=3, cursor="hand2")
        btn.pack()
        self._btn_labels[applet["id"]] = btn
        if not active:
            btn.bind("<Button-1>", lambda e, a=applet: self._launch_applet(a))
            btn.bind("<Enter>", lambda e: btn.config(bg=C["mauve"]))
            btn.bind("<Leave>", lambda e, c=btn_bg: btn.config(bg=c))

    def _start_poll(self):
        def poll():
            while self._alive:
                time.sleep(5)
                if not (self.root and self._alive):
                    break
                new_status = {}
                for a in APPLETS:
                    new_status[a["id"]] = _is_running(a["script"])
                self._status = new_status
                for aid in list(self._procs):
                    try:
                        if self._procs[aid].poll() is not None:
                            del self._procs[aid]
                    except Exception:
                        self._procs.pop(aid, None)
                try:
                    if self.root and self.root.winfo_exists():
                        self.root.after(0, self._update_status)
                except Exception:
                    break
        threading.Thread(target=poll, daemon=True).start()

    def _update_status(self):
        for a in APPLETS:
            active = self._status.get(a["id"], False)
            dot = self._dot_labels.get(a["id"])
            btn = self._btn_labels.get(a["id"])
            if dot:
                if active:
                    dot.config(text="\u25cf Running", fg=C["green"])
                else:
                    dot.config(text="\u25cb Stopped", fg=C["dim"])
            if btn:
                if active:
                    btn.config(text="Running", fg=C["green"], bg=C["card"])
                    btn.unbind("<Button-1>")
                    btn.unbind("<Enter>")
                    btn.unbind("<Leave>")
                else:
                    accent = a["colour"]
                    btn.config(text="Launch", fg=C["bg"], bg=accent)
                    btn.bind("<Button-1>",
                             lambda e, ap=a: self._launch_applet(ap))
                    btn.bind("<Enter>", lambda e: btn.config(bg=C["mauve"]))
                    btn.bind("<Leave>",
                             lambda e, c=accent: btn.config(bg=c))
        if self._stats_frame:
            self._render_stats()

    def _launch_applet(self, applet):
        lock = self._launch_locks[applet["id"]]
        if not lock.acquire(blocking=False):
            return
        try:
            if _is_running(applet["script"]):
                return
            proc = subprocess.Popen(
                [PYTHONW, str(SCRIPT_DIR / applet["script"])],
                creationflags=DETACHED)
            self._procs[applet["id"]] = proc
            with self._config_lock:
                self.config = _load_config()
                launches = self.config.setdefault("launches", {})
                launches[applet["id"]] = launches.get(applet["id"], 0) + 1
                self.config["total_launches"] = self.config.get(
                    "total_launches", 0) + 1
                self.config["xp"] = self.config.get("xp", 0) + 10
                level = self.config.get("level", 1)
                if self.config["xp"] >= level * 50:
                    self.config["xp"] -= level * 50
                    self.config["level"] = level + 1
                _save_config(self.config)
            self.root.after(2000, self._rebuild)
        finally:
            lock.release()

    def _launch_all(self):
        for a in APPLETS:
            if not _is_running(a["script"]):
                self._launch_applet(a)

    def _stop_all(self):
        for proc in self._procs.values():
            try: proc.terminate()
            except Exception: pass
        self._procs.clear()
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                if proc.info["pid"] == MY_PID:
                    continue
                try:
                    if "python" not in (proc.info.get("name") or "").lower():
                        continue
                    cmd_str = " ".join(
                        str(c) for c in (proc.info.get("cmdline") or []))
                    for s in [a["script"] for a in APPLETS]:
                        if s in cmd_str:
                            proc.terminate()
                            break
                except Exception:
                    pass
        except ImportError:
            pass
        self.root.after(1500, self._rebuild)

    def _rebuild(self):
        if not self.root or self._rebuilding:
            return
        self._rebuilding = True
        try:
            if self._clock_id is not None:
                self.root.after_cancel(self._clock_id)
                self._clock_id = None
            for w in self.root.winfo_children():
                w.destroy()
            self._photo_refs = []
            self._dot_labels = {}
            self._btn_labels = {}
            with self._config_lock:
                self.config = _load_config()
            self._build()
            self.root.update_idletasks()
        except Exception:
            pass
        finally:
            self._rebuilding = False

    def _tick_clock(self):
        if self.root and self._alive:
            try:
                self._clock_lbl.config(
                    text=datetime.now().strftime("%H:%M:%S"))
                self._clock_id = self.root.after(1000, self._tick_clock)
            except Exception:
                self._clock_id = None

    def _close(self):
        self._alive = False
        if self._clock_id is not None:
            try: self.root.after_cancel(self._clock_id)
            except Exception: pass
            self._clock_id = None
        try: self.root.destroy()
        except Exception: pass
        self.root = None


def main():
    _kill_old_suite()
    app = Launcher()

    def on_show(icon, item):
        threading.Thread(target=app.show, daemon=True).start()

    def on_quit(icon, item):
        app._alive = False
        if app.root:
            try: app.root.destroy()
            except Exception: pass
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open Launcher", on_show, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Launcher", on_quit),
    )
    icon = pystray.Icon("move_in", _tray_icon(),
                        f"Move In v{__version__}", menu)
    threading.Timer(0.5, lambda: threading.Thread(
        target=app.show, daemon=True).start()).start()
    icon.run()


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("launcher.py")
    main()
