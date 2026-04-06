"""
Lawrence: Move In — Window Tiles v2.0.0
Coloured tile launcher for every visible window. Grouped by app category.
Includes a full-screen Desktop Canvas overlay with draggable tiles and zones.
"""

__version__ = "2.0.0"

import ctypes
import json
import os
import threading
import time
import tkinter as tk
from tkinter import simpledialog
from pathlib import Path
from collections import defaultdict

import pystray
from PIL import Image, ImageDraw, ImageFont, ImageTk
import win32gui
import win32con
import win32process
import win32api


# ────────────────────────────────────────────────────────────────
# 1. CONSTANTS & CONFIG
# ────────────────────────────────────────────────────────────────

TILES_CONFIG = Path(__file__).parent / "tiles_config.json"
CANVAS_CONFIG = Path(__file__).parent / "canvas_config.json"
REFRESH_INTERVAL = 2.0
CANVAS_REFRESH = 4.0
SEARCH_DEBOUNCE_MS = 250

# Catppuccin-inspired palette
C = {
    "bg":       "#0f0f1a",  "surface":  "#1a1a2e",  "card":     "#242440",
    "card_hi":  "#363660",  "border":   "#3a3a5c",  "text":     "#cdd6f4",
    "dim":      "#6c7086",  "blue":     "#89b4fa",  "green":    "#a6e3a1",
    "red":      "#f38ba8",  "peach":    "#fab387",  "mauve":    "#cba6f7",
    "teal":     "#94e2d5",  "yellow":   "#f9e2af",  "pink":     "#f5c2e7",
    "sky":      "#89dceb",  "white":    "#ffffff",  "lavender": "#b4befe",
}

# (icon_text, display_name, group, icon_bg_colour)
APP_META = {
    "chrome.exe":          ("G",  "Chrome",    "Browsers",  "#4285F4"),
    "msedge.exe":          ("E",  "Edge",      "Browsers",  "#0078D7"),
    "firefox.exe":         ("Fx", "Firefox",   "Browsers",  "#FF7139"),
    "brave.exe":           ("B",  "Brave",     "Browsers",  "#FB542B"),
    "Code.exe":            ("{}", "VS Code",   "Dev",       "#007ACC"),
    "code.exe":            ("{}", "VS Code",   "Dev",       "#007ACC"),
    "devenv.exe":          ("VS", "Visual S.", "Dev",       "#68217A"),
    "notepad.exe":         ("N",  "Notepad",   "Dev",       "#6B9F1E"),
    "Notepad.exe":         ("N",  "Notepad",   "Dev",       "#6B9F1E"),
    "notepad++.exe":       ("N+", "Npp",       "Dev",       "#90E59A"),
    "WindowsTerminal.exe": (">_", "Terminal",  "Terminals", "#4D4D4D"),
    "cmd.exe":             (">",  "CMD",       "Terminals", "#1E1E1E"),
    "powershell.exe":      ("PS", "PShell",    "Terminals", "#012456"),
    "pwsh.exe":            ("PS", "PShell",    "Terminals", "#012456"),
    "python.exe":          ("Py", "Python",    "Terminals", "#306998"),
    "pythonw.exe":         ("Py", "Python",    "Terminals", "#306998"),
    "node.exe":            ("JS", "Node",      "Terminals", "#339933"),
    "WINWORD.EXE":         ("W",  "Word",      "Office",    "#2B579A"),
    "EXCEL.EXE":           ("X",  "Excel",     "Office",    "#217346"),
    "POWERPNT.EXE":        ("P",  "PowerPnt",  "Office",    "#D24726"),
    "OUTLOOK.EXE":         ("O",  "Outlook",   "Office",    "#0078D4"),
    "ONENOTE.EXE":         ("ON", "OneNote",   "Office",    "#7719AA"),
    "Teams.exe":           ("T",  "Teams",     "Comms",     "#6264A7"),
    "ms-teams.exe":        ("T",  "Teams",     "Comms",     "#6264A7"),
    "slack.exe":           ("#",  "Slack",     "Comms",     "#4A154B"),
    "Slack.exe":           ("#",  "Slack",     "Comms",     "#4A154B"),
    "Discord.exe":         ("D",  "Discord",   "Comms",     "#5865F2"),
    "discord.exe":         ("D",  "Discord",   "Comms",     "#5865F2"),
    "Telegram.exe":        ("Tg", "Telegram",  "Comms",     "#0088CC"),
    "telegram.exe":        ("Tg", "Telegram",  "Comms",     "#0088CC"),
    "Spotify.exe":         ("S",  "Spotify",   "Media",     "#1DB954"),
    "spotify.exe":         ("S",  "Spotify",   "Media",     "#1DB954"),
    "vlc.exe":             ("V",  "VLC",       "Media",     "#FF8800"),
    "explorer.exe":        ("F",  "Explorer",  "Files",     "#FFB900"),
    "mstsc.exe":           ("RD", "RDP",       "Remote",    "#0078D4"),
    "ShadowPC.exe":        ("Sh", "Shadow",    "Remote",    "#7B2FF7"),
    "Taskmgr.exe":         ("TM", "Task Mgr",  "System",    "#E8710A"),
    "SystemSettings.exe":  ("S",  "Settings",  "System",    "#4C4C4C"),
    "osk.exe":             ("KB", "Keyboard",  "System",    "#4C4C4C"),
    "Figma.exe":           ("Fi", "Figma",     "Design",    "#F24E1E"),
    "figma.exe":           ("Fi", "Figma",     "Design",    "#F24E1E"),
    "Obsidian.exe":        ("Ob", "Obsidian",  "Notes",     "#7C3AED"),
    "Notion.exe":          ("No", "Notion",    "Notes",     "#000000"),
    "claude.exe":          ("Cl", "Claude",    "AI",        "#D97706"),
}

# (icon_char, accent_colour, header_bg) — modified at runtime for custom groups
GROUP_META = {
    "Browsers":  ("B", C["blue"],     "#1a2640"),
    "Dev":       ("D", C["mauve"],    "#261a40"),
    "Terminals": (">", C["dim"],      "#1a1a26"),
    "Office":    ("O", C["green"],    "#1a2618"),
    "Comms":     ("C", C["pink"],     "#261a26"),
    "Media":     ("M", C["teal"],     "#1a2626"),
    "Files":     ("F", C["yellow"],   "#26261a"),
    "Remote":    ("R", C["sky"],      "#1a2630"),
    "System":    ("S", C["peach"],    "#261e1a"),
    "Design":    ("D", C["pink"],     "#261a22"),
    "Notes":     ("N", C["lavender"], "#1e1a30"),
    "AI":        ("A", C["mauve"],    "#221a30"),
    "Other":     ("?", C["dim"],      "#1a1a22"),
}


# ────────────────────────────────────────────────────────────────
# 2. ICON RENDERING (PIL Image cache — NOT PhotoImage)
# ────────────────────────────────────────────────────────────────

_icon_cache: dict[tuple, Image.Image] = {}
_ICON_CACHE_MAX = 200


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def render_icon(text: str, bg_color: str, size: int = 36) -> Image.Image:
    """Return a PIL Image with a rounded-rect icon. Cached (max 200)."""
    key = (text, bg_color, size)
    if key in _icon_cache:
        return _icon_cache[key]

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rgb = _hex_to_rgb(bg_color) if bg_color.startswith("#") else (100, 100, 140)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=min(10, size // 3), fill=rgb)

    font_size = size // 2 if len(text) <= 2 else size // 3
    try:
        fnt = ImageFont.truetype("segoeuib.ttf", font_size)
    except Exception:
        try:
            fnt = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            fnt = ImageFont.load_default()
    d.text((size // 2, size // 2), text, fill="white", font=fnt, anchor="mm")

    # Evict oldest entries if cache is full
    if len(_icon_cache) >= _ICON_CACHE_MAX:
        for old_key in list(_icon_cache.keys())[:_ICON_CACHE_MAX // 4]:
            del _icon_cache[old_key]
    _icon_cache[key] = img
    return img


def _to_photo(pil_img: Image.Image) -> ImageTk.PhotoImage:
    """Convert PIL Image to PhotoImage for tkinter display."""
    return ImageTk.PhotoImage(pil_img)


# ────────────────────────────────────────────────────────────────
# 3. WINDOW HELPERS
# ────────────────────────────────────────────────────────────────

def get_visible_windows() -> list[tuple]:
    """Return [(hwnd, title, exe_name, is_minimised), ...]."""
    results = []
    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or title in ("Program Manager", "Windows Input Experience"):
            return
        r = win32gui.GetWindowRect(hwnd)
        if (r[2] - r[0]) < 50 or (r[3] - r[1]) < 50:
            return
        is_min = bool(win32gui.IsIconic(hwnd))
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            h = win32api.OpenProcess(0x0410, False, pid)
            exe = os.path.basename(win32process.GetModuleFileNameEx(h, 0))
            win32api.CloseHandle(h)
        except Exception:
            exe = "unknown"
        results.append((hwnd, title, exe, is_min))
    win32gui.EnumWindows(_enum, None)
    return results


def get_app_meta(exe: str, title: str = "") -> tuple:
    """Return (icon_text, display_name, group, bg_colour) for an exe."""
    if exe in APP_META:
        return APP_META[exe]
    clean = exe.replace(".exe", "").replace("_", " ")
    letter = clean[0].upper() if clean else "?"
    combined = (title + clean).lower()
    if any(w in combined for w in ("browser", "http", "web")):
        return (letter, clean.title()[:9], "Browsers", C["blue"])
    if any(w in combined for w in ("terminal", "shell", "bash")):
        return (letter, clean.title()[:9], "Terminals", "#4D4D4D")
    if any(w in combined for w in ("chat", "message")):
        return (letter, clean.title()[:9], "Comms", C["pink"])
    return (letter, clean.title()[:9], "Other", "#444466")


def focus_window(hwnd: int):
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


def minimize_window(hwnd: int):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────
# 4. CONFIG I/O (thread-safe)
# ────────────────────────────────────────────────────────────────

_config_lock = threading.Lock()
_canvas_config_lock = threading.Lock()

_TILES_DEFAULT = {"custom_groups": {}, "collapsed": [], "locked": False, "locked_order": {}}
_CANVAS_DEFAULT = {"tile_positions": {}, "zones": []}


def _load_json(path: Path, default: dict, lock: threading.Lock) -> dict:
    with lock:
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return dict(default)


def _save_json(path: Path, data: dict, lock: threading.Lock):
    with lock:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


def load_config():
    return _load_json(TILES_CONFIG, _TILES_DEFAULT, _config_lock)

def save_config(cfg):
    _save_json(TILES_CONFIG, cfg, _config_lock)

def load_canvas_config():
    return _load_json(CANVAS_CONFIG, _CANVAS_DEFAULT, _canvas_config_lock)

def save_canvas_config(cfg):
    _save_json(CANVAS_CONFIG, cfg, _canvas_config_lock)


# ────────────────────────────────────────────────────────────────
# 5. SHARED UI HELPERS
# ────────────────────────────────────────────────────────────────

def _styled_menu(parent) -> tk.Menu:
    return tk.Menu(parent, tearoff=0, bg=C["surface"], fg=C["text"],
                   activebackground=C["card_hi"], activeforeground=C["white"],
                   font=("Segoe UI", 9))


def _show_tooltip(root, x, y, text) -> tk.Toplevel:
    tw = tk.Toplevel(root)
    tw.wm_overrideredirect(True)
    tw.attributes("-topmost", True)
    tw.configure(bg=C["border"])
    display = (text[:90] + "...") if len(text) > 90 else text
    tk.Label(tw, text=display, font=("Segoe UI", 9), bg=C["surface"],
             fg=C["text"], padx=8, pady=3, wraplength=320, justify="left").pack(padx=1, pady=1)
    tw.geometry(f"+{x}+{y}")
    return tw


def _destroy_tooltip(tw):
    if tw:
        try:
            tw.destroy()
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────
# 6. TilesWindow — compact sidebar
# ────────────────────────────────────────────────────────────────

class TilesWindow:
    TILE_SIZE = 82
    COLS = 5

    def __init__(self):
        self.root = None
        self.config = load_config()
        self.collapsed = set(self.config.get("collapsed", []))
        self.locked = self.config.get("locked", False)
        self._locked_order = self.config.get("locked_order", {})
        self._alive = True
        self._tooltip_win = None
        self._drag_xy = (0, 0)
        self._resize_start = None
        self._last_snap = None
        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._show_lock = threading.Lock()
        self._redrawing = False
        self._search_after_id = None

    # --- Lifecycle ---

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
        self.root.title(f"Window Tiles v{__version__}")
        self.root.configure(bg=C["bg"])
        self.root.attributes("-topmost", True, "-alpha", 0.96)
        self.root.geometry("480x680+30+40")
        self.root.minsize(240, 200)
        self._build()
        self._make_draggable()
        self._make_resizable()
        self._start_refresh()
        self.root.mainloop()

    def _close(self):
        self._alive = False
        _destroy_tooltip(self._tooltip_win)
        self._tooltip_win = None
        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.root.destroy()
        self.root = None

    # --- Draggable title bar ---

    def _make_draggable(self):
        def start(e): self._drag_xy = (e.x, e.y)
        def drag(e):
            self.root.geometry(f"+{self.root.winfo_x() + e.x - self._drag_xy[0]}"
                               f"+{self.root.winfo_y() + e.y - self._drag_xy[1]}")
        for w in (self._header,) + tuple(self._header.winfo_children()):
            w.bind("<Button-1>", start)
            w.bind("<B1-Motion>", drag)

    def _make_resizable(self):
        grip = tk.Label(self.root, text="\u25E2", font=("Segoe UI", 10),
                        fg=C["dim"], bg=C["bg"], cursor="size_nw_se")
        grip.place(relx=1.0, rely=1.0, anchor="se")
        def start(e):
            self._resize_start = (e.x_root, e.y_root,
                                  self.root.winfo_width(), self.root.winfo_height())
        def resize(e):
            if not self._resize_start:
                return
            nw = max(240, self._resize_start[2] + e.x_root - self._resize_start[0])
            nh = max(200, self._resize_start[3] + e.y_root - self._resize_start[1])
            self.root.geometry(f"{nw}x{nh}")
        grip.bind("<Button-1>", start)
        grip.bind("<B1-Motion>", resize)

    # --- Build UI ---

    def _build(self):
        # Title bar (28px)
        self._header = tk.Frame(self.root, bg=C["surface"], height=28)
        self._header.pack(fill="x")
        self._header.pack_propagate(False)
        tk.Label(self._header, text=f"\u25A6  Window Tiles v{__version__}",
                 font=("Segoe UI Semibold", 9), bg=C["surface"], fg=C["text"]).pack(side="left", padx=8)
        close_btn = tk.Label(self._header, text="\u2715", font=("Segoe UI", 9),
                             bg=C["surface"], fg=C["dim"], cursor="hand2", padx=8)
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self._close())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg=C["red"]))
        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=C["dim"]))
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x")

        # Search bar
        sf = tk.Frame(self.root, bg=C["bg"])
        sf.pack(fill="x", padx=10, pady=(6, 2))
        s_outer = tk.Frame(sf, bg=C["border"], padx=1, pady=1)
        s_outer.pack(fill="x")
        s_inner = tk.Frame(s_outer, bg=C["surface"])
        s_inner.pack(fill="x")
        tk.Label(s_inner, text=" \u2315 ", font=("Segoe UI", 10),
                 fg=C["dim"], bg=C["surface"]).pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._debounced_redraw())
        tk.Entry(s_inner, textvariable=self._search_var, bg=C["surface"], fg=C["text"],
                 insertbackground=C["text"], font=("Segoe UI", 10),
                 relief="flat", bd=0).pack(fill="x", ipady=3, padx=(0, 6), side="left", expand=True)

        # Scrollable area
        container = tk.Frame(self.root, bg=C["bg"])
        container.pack(fill="both", expand=True, padx=2, pady=2)
        self._canvas = tk.Canvas(container, bg=C["bg"], highlightthickness=0)
        vsb = tk.Scrollbar(container, orient="vertical", command=self._canvas.yview, width=6)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(fill="both", expand=True)
        self._inner = tk.Frame(self._canvas, bg=C["bg"])
        self._cw = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", lambda e: self._canvas.config(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(self._cw, width=e.width))

        # Scoped mousewheel
        def _mw(e):
            try:
                if self.root and self.root.winfo_exists():
                    self._canvas.yview_scroll(-(e.delta // 120), "units")
            except Exception:
                pass
        self._canvas.bind("<Enter>", lambda e: self.root.bind_all("<MouseWheel>", _mw))
        self._canvas.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))

        # Bottom bar
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x", side="bottom")
        bottom = tk.Frame(self.root, bg=C["surface"], height=24)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        self._count_lbl = tk.Label(bottom, text="", font=("Segoe UI", 8),
                                   bg=C["surface"], fg=C["dim"])
        self._count_lbl.pack(side="left", padx=6)
        lt = "\U0001F512 locked" if self.locked else "\U0001F513 unlock"
        lc = C["yellow"] if self.locked else C["dim"]
        self._lock_btn = tk.Label(bottom, text=lt, font=("Segoe UI Emoji", 7),
                                  bg=C["surface"], fg=lc, cursor="hand2")
        self._lock_btn.pack(side="right", padx=4)
        self._lock_btn.bind("<Button-1>", lambda e: self._toggle_lock())
        for txt, cmd in [("expand", self._expand_all), ("collapse", self._collapse_all)]:
            b = tk.Label(bottom, text=txt, font=("Segoe UI", 7),
                         bg=C["surface"], fg=C["blue"], cursor="hand2")
            b.pack(side="right", padx=4)
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b: w.config(fg=C["lavender"]))
            b.bind("<Leave>", lambda e, w=b: w.config(fg=C["blue"]))

        self._force_redraw()

    # --- Refresh logic ---

    def _debounced_redraw(self):
        if self._search_after_id is not None:
            try:
                self.root.after_cancel(self._search_after_id)
            except Exception:
                pass
        self._search_after_id = self.root.after(SEARCH_DEBOUNCE_MS, self._force_redraw)

    def _snapshot(self):
        groups = self._get_groups()
        return tuple(sorted(
            (g, tuple((w["hwnd"], w["title"][:30], w["minimized"]) for w in ws))
            for g, ws in groups.items()
        ))

    def _start_refresh(self):
        def _check():
            try:
                snap = self._snapshot()
                if snap != self._last_snap:
                    self._last_snap = snap
                    self._redraw()
            except Exception:
                pass
        def _loop():
            while self._alive:
                time.sleep(REFRESH_INTERVAL)
                if not self.root or not self._alive:
                    break
                try:
                    self.root.after(0, _check)
                except Exception:
                    break
        threading.Thread(target=_loop, daemon=True).start()

    def _force_redraw(self):
        self._last_snap = None
        self._redraw()

    # --- Grouping ---

    def _get_groups(self) -> dict:
        windows = get_visible_windows()
        custom = self.config.get("custom_groups", {})
        search = self._search_var.get().lower().strip() if hasattr(self, "_search_var") else ""
        groups = defaultdict(list)
        for hwnd, title, exe, is_min in windows:
            if "Window Tiles" in title:
                continue
            icon_text, name, auto_grp, icon_bg = get_app_meta(exe, title)
            grp = custom.get(exe, auto_grp)
            if search and search not in f"{name} {title} {grp} {exe}".lower():
                continue
            groups[grp].append({"hwnd": hwnd, "title": title, "exe": exe,
                                "icon_text": icon_text, "icon_bg": icon_bg,
                                "name": name, "minimized": is_min})
        # Apply locked order
        if self.locked and self._locked_order:
            for grp, wins in groups.items():
                if grp in self._locked_order:
                    order = self._locked_order[grp]
                    groups[grp] = sorted(wins, key=lambda w: (
                        order.index(k) if (k := f"{w['exe']}|{w['title'][:60]}") in order else 9999))
        return dict(groups)

    # --- Drawing ---

    def _redraw(self):
        if self._redrawing:
            return
        self._redrawing = True
        try:
            self._photo_refs = []
            for w in self._inner.winfo_children():
                w.destroy()
            groups = self._get_groups()
            total = sum(len(v) for v in groups.values())
            self._count_lbl.config(text=f"{total} windows")
            if not groups:
                tk.Label(self._inner, text="Nothing open", font=("Segoe UI", 12),
                         fg=C["dim"], bg=C["bg"]).pack(pady=40)
                return
            for grp in sorted(groups, key=lambda g: (0 if g in GROUP_META else 1, g)):
                self._draw_group(grp, groups[grp])
        except Exception:
            pass
        finally:
            self._redrawing = False

    def _draw_group(self, name, windows):
        g_icon, g_accent, g_hdr_bg = GROUP_META.get(name, ("?", C["dim"], "#1a1a22"))
        collapsed = name in self.collapsed

        # Group header with coloured accent stripe
        hdr_outer = tk.Frame(self._inner, bg=C["bg"])
        hdr_outer.pack(fill="x", padx=4, pady=(6, 0))
        tk.Frame(hdr_outer, bg=g_accent, width=4).pack(side="left", fill="y")
        hdr = tk.Frame(hdr_outer, bg=g_hdr_bg, cursor="hand2")
        hdr.pack(fill="x", side="left", expand=True, ipady=3)

        arrow = "\u25B8" if collapsed else "\u25BE"
        tk.Label(hdr, text=f" {arrow}", font=("Segoe UI", 8), fg=g_accent, bg=g_hdr_bg).pack(side="left")
        gi_photo = _to_photo(render_icon(g_icon, g_accent, 18))
        self._photo_refs.append(gi_photo)
        tk.Label(hdr, image=gi_photo, bg=g_hdr_bg).pack(side="left", padx=(4, 5))
        tk.Label(hdr, text=name, font=("Segoe UI", 10, "bold"), fg=g_accent, bg=g_hdr_bg).pack(side="left")
        pill = tk.Frame(hdr, bg=g_accent, padx=6)
        pill.pack(side="left", padx=(8, 0))
        tk.Label(pill, text=str(len(windows)), font=("Segoe UI", 7, "bold"),
                 fg=g_hdr_bg, bg=g_accent).pack()

        # Bind click-to-collapse on all header widgets
        for w in [hdr_outer, hdr] + list(hdr.winfo_children()):
            w.bind("<Button-1>", lambda e, n=name: self._toggle_collapse(n))
        hdr.bind("<Button-3>", lambda e, n=name, ws=windows: self._group_menu(e, n, ws))

        if collapsed:
            # Mini icon strip when collapsed
            strip = tk.Frame(self._inner, bg=C["bg"])
            strip.pack(fill="x", padx=20, pady=(3, 0))
            for w in windows[:12]:
                si = _to_photo(render_icon(w["icon_text"], w["icon_bg"], 16))
                self._photo_refs.append(si)
                sl = tk.Label(strip, image=si, bg=C["bg"], cursor="hand2")
                sl.pack(side="left", padx=2)
                sl.bind("<Button-1>", lambda e, h=w["hwnd"]: focus_window(h))
            if len(windows) > 12:
                tk.Label(strip, text=f"+{len(windows)-12}", font=("Segoe UI", 7),
                         fg=C["dim"], bg=C["bg"]).pack(side="left", padx=4)
            return

        # Tile grid
        grid = tk.Frame(self._inner, bg=C["bg"])
        grid.pack(fill="x", padx=8, pady=(3, 0))
        for i, w in enumerate(windows):
            self._draw_tile(grid, w, g_accent, i)

    def _draw_tile(self, parent, winfo, accent, idx):
        is_min = winfo["minimized"]
        bg = C["card"] if not is_min else C["surface"]
        fg = C["text"] if not is_min else C["dim"]

        tile = tk.Frame(parent, bg=bg, width=self.TILE_SIZE, height=self.TILE_SIZE, cursor="hand2")
        tile.pack_propagate(False)
        tile.grid(row=idx // self.COLS, column=idx % self.COLS, padx=3, pady=3)
        tk.Frame(tile, bg=(accent if not is_min else C["border"]), height=3).pack(fill="x")

        icon_photo = _to_photo(render_icon(winfo["icon_text"],
                                           winfo["icon_bg"] if not is_min else "#333344", 34))
        self._photo_refs.append(icon_photo)
        ilbl = tk.Label(tile, image=icon_photo, bg=bg)
        ilbl.pack(pady=(4, 2))
        nlbl = tk.Label(tile, text=winfo["name"][:9], font=("Segoe UI", 7), bg=bg, fg=fg)
        nlbl.pack()
        if is_min:
            tk.Label(tile, text="\u2012", font=("Segoe UI", 5), bg=bg, fg=C["dim"]).pack()

        widgets = [tile, ilbl, nlbl]
        for w in widgets:
            w.bind("<Button-1>", lambda e, h=winfo["hwnd"]: focus_window(h))
            w.bind("<Button-3>", lambda e, wi=winfo: self._tile_menu(e, wi))
            w.bind("<Enter>", lambda e: self._tile_hover(tile, widgets, winfo, True))
            w.bind("<Leave>", lambda e, b=bg: self._tile_hover(tile, widgets, winfo, False, b))

    def _tile_hover(self, tile, widgets, winfo, entering, restore_bg=None):
        new_bg = C["card_hi"] if entering else (restore_bg or C["card"])
        for w in widgets:
            try:
                w.configure(bg=new_bg)
            except Exception:
                pass
        if entering:
            _destroy_tooltip(self._tooltip_win)
            x, y = tile.winfo_rootx(), tile.winfo_rooty() + tile.winfo_height() + 2
            self._tooltip_win = _show_tooltip(self.root, x, y, winfo["title"])
        else:
            _destroy_tooltip(self._tooltip_win)
            self._tooltip_win = None

    # --- Lock / Collapse ---

    def _toggle_collapse(self, name):
        self.collapsed.symmetric_difference_update({name})
        self.config["collapsed"] = list(self.collapsed)
        save_config(self.config)
        self._force_redraw()

    def _collapse_all(self):
        self.collapsed = set(self._get_groups().keys())
        self.config["collapsed"] = list(self.collapsed)
        save_config(self.config)
        self._force_redraw()

    def _expand_all(self):
        self.collapsed.clear()
        self.config["collapsed"] = []
        save_config(self.config)
        self._force_redraw()

    def _toggle_lock(self):
        self.locked = not self.locked
        if self.locked:
            groups = self._get_groups()
            self._locked_order = {g: [f"{w['exe']}|{w['title'][:60]}" for w in ws]
                                  for g, ws in groups.items()}
            self.config["locked_order"] = self._locked_order
        self.config["locked"] = self.locked
        save_config(self.config)
        lt = "\U0001F512 locked" if self.locked else "\U0001F513 unlock"
        self._lock_btn.config(text=lt, fg=C["yellow"] if self.locked else C["dim"])
        self._force_redraw()

    # --- Context menus ---

    def _tile_menu(self, event, winfo):
        m = _styled_menu(self.root)
        m.add_command(label="Focus", command=lambda: focus_window(winfo["hwnd"]))
        m.add_command(label="Minimise", command=lambda: minimize_window(winfo["hwnd"]))
        m.add_separator()
        gm = _styled_menu(m)
        for gname in sorted(GROUP_META):
            gi, gc, _ = GROUP_META[gname]
            gm.add_command(label=f"  {gi}  {gname}",
                           command=lambda g=gname, e=winfo["exe"]: self._move_group(e, g))
        gm.add_separator()
        gm.add_command(label="+ Custom group...", command=lambda: self._new_group(winfo["exe"]))
        m.add_cascade(label="Move to group", menu=gm)
        m.tk_popup(event.x_root, event.y_root)

    def _group_menu(self, event, name, windows):
        m = _styled_menu(self.root)
        m.add_command(label=f"Focus all {name}",
                      command=lambda: [focus_window(w["hwnd"]) for w in windows])
        m.add_command(label=f"Minimise all {name}",
                      command=lambda: [minimize_window(w["hwnd"]) for w in windows])
        m.tk_popup(event.x_root, event.y_root)

    def _move_group(self, exe, group):
        self.config.setdefault("custom_groups", {})[exe] = group
        save_config(self.config)
        self._force_redraw()

    def _new_group(self, exe):
        self.root.attributes("-topmost", False)
        try:
            result = simpledialog.askstring("New Group", "Group name:", parent=self.root)
        finally:
            self.root.attributes("-topmost", True)
        if result and result.strip():
            g = result.strip()
            if g not in GROUP_META:
                GROUP_META[g] = (g[0].upper(), C["lavender"], "#1e1a30")
            self._move_group(exe, g)


# ────────────────────────────────────────────────────────────────
# 7. DesktopCanvas — full-screen overlay
# ────────────────────────────────────────────────────────────────

class DesktopCanvas:
    TILE_W, TILE_H = 80, 80
    ZONE_MIN = 60
    ALPHA_NORMAL, ALPHA_PASSTHROUGH = 0.88, 0.08
    # Win32 constants
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_LAYERED = 0x00080000
    GWL_EXSTYLE = -20

    def __init__(self):
        self.root = None
        self.config = load_canvas_config()
        self._alive = True
        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._tile_photo_map: dict[str, list] = {}
        self._tooltip_win = None
        self._tile_widgets: dict[str, tk.Frame] = {}
        self._zone_start = None
        self._zone_rect_id = None
        self.mode = "normal"
        self._passthrough = False
        self._hwnd = None
        self._show_lock = threading.Lock()

    # --- Lifecycle ---

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
        self.root.title(f"Desktop Canvas v{__version__}")
        self.root.attributes("-topmost", True, "-alpha", self.ALPHA_NORMAL)
        self.root.configure(bg="#0a0a14")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{sw}x{sh}+0+0")
        self.sw, self.sh = sw, sh
        self._build()
        self._populate()
        self._start_refresh()
        self._start_focus_monitor()
        self.root.update_idletasks()
        self._hwnd = self._find_hwnd()
        self.root.mainloop()

    def _close(self):
        if self._passthrough:
            self._exit_passthrough()
        self._alive = False
        _destroy_tooltip(self._tooltip_win)
        self._tooltip_win = None
        try:
            self.root.destroy()
        except Exception:
            pass
        self.root = None

    def _find_hwnd(self):
        result = [None]
        def _enum(hwnd, _):
            try:
                if "Desktop Canvas" in win32gui.GetWindowText(hwnd):
                    result[0] = hwnd
            except Exception:
                pass
        try:
            win32gui.EnumWindows(_enum, None)
        except Exception:
            pass
        return result[0]

    # --- Build UI ---

    def _build(self):
        # Toolbar
        tb = tk.Frame(self.root, bg="#0d0d1e", height=40)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        tk.Label(tb, text=f"\u25A6  Desktop Canvas v{__version__}", font=("Segoe UI Semibold", 10),
                 fg=C["blue"], bg="#0d0d1e").pack(side="left", padx=12)

        # Mode badge
        self._mode_frame = tk.Frame(tb, bg=C["green"], padx=8, pady=1)
        self._mode_frame.pack(side="left", padx=(16, 0), pady=8)
        self._mode_lbl = tk.Label(self._mode_frame, text="NAVIGATE",
                                  font=("Segoe UI", 8, "bold"), fg="#0d0d1e", bg=C["green"])
        self._mode_lbl.pack()

        # Passthrough button
        self._pt_border = tk.Frame(tb, bg=C["sky"], padx=1, pady=1)
        self._pt_border.pack(side="left", padx=(16, 0), pady=7)
        self._pt_btn = tk.Label(self._pt_border, text="\u25CB  Passthrough",
                                font=("Segoe UI", 8, "bold"), fg=C["sky"], bg="#0d0d1e",
                                padx=10, pady=2, cursor="hand2")
        self._pt_btn.pack()
        self._pt_btn.bind("<Button-1>", lambda e: self._toggle_passthrough())
        self._pt_btn.bind("<Enter>", lambda e: self._pt_btn.config(bg="#1a1a30"))
        self._pt_btn.bind("<Leave>", lambda e: self._pt_btn.config(bg="#0d0d1e"))

        # Right-side buttons
        btn_bg, btn_hover = "#181830", "#282850"
        for txt, col, cmd in [
            ("\u2715  Exit",       C["dim"],    self._close),
            ("\u21BA  Reset",      C["peach"],  self._reset_positions),
            ("\u2716  Clear Zones", C["red"],   self._clear_zones),
            ("\u25A1  Draw Zone",  C["yellow"], self._toggle_draw_mode),
        ]:
            border = tk.Frame(tb, bg=col, padx=1, pady=1)
            border.pack(side="right", padx=3, pady=7)
            b = tk.Label(border, text=txt, font=("Segoe UI", 8, "bold"),
                         fg=col, bg=btn_bg, padx=8, pady=1, cursor="hand2")
            b.pack()
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b: w.config(bg=btn_hover))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=btn_bg))

        self._cv_count = tk.Label(tb, text="", font=("Segoe UI", 8), fg=C["dim"], bg="#0d0d1e")
        self._cv_count.pack(side="right", padx=12)
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x")

        # Canvas area
        self._cv = tk.Canvas(self.root, bg="#0a0a14", highlightthickness=0, cursor="arrow")
        self._cv.pack(fill="both", expand=True)
        self._draw_zones()
        self._cv.bind("<Button-1>", self._cv_click)
        self._cv.bind("<B1-Motion>", self._cv_drag)
        self._cv.bind("<ButtonRelease-1>", self._cv_release)
        self._cv.bind("<Button-3>", self._cv_right_click)
        self.root.bind("<Escape>", lambda e: self._close())

    # --- Zone rendering ---

    def _draw_zones(self):
        self._cv.delete("zone")
        for i, z in enumerate(self.config.get("zones", [])):
            x1, y1, x2, y2 = z["x1"], z["y1"], z["x2"], z["y2"]
            colour = z.get("colour", C["blue"])
            name = z.get("name", f"Zone {i+1}")
            self._cv.create_rectangle(x1, y1, x2, y2, outline=colour, fill="",
                                      width=3, dash=(8, 5), tags=("zone",))
            self._cv.create_rectangle(x1+2, y1+2, x2-2, y2-2, outline="", fill=colour,
                                      stipple="gray12", tags=("zone",))
            # Label pill
            approx_w = len(name) * 7 + 24
            lx, ly = x1 + 8, y1 + 6
            self._cv.create_rectangle(lx, ly, lx + approx_w, ly + 20,
                                      outline=colour, fill="#0a0a14", width=1, tags=("zone",))
            self._cv.create_text(lx + approx_w // 2, ly + 10, text=name, anchor="center",
                                 font=("Segoe UI", 9, "bold"), fill=colour, tags=("zone",))

    # --- Tile population ---

    def _populate(self):
        self._photo_refs = []
        self._tile_photo_map = {}
        for w in self._tile_widgets.values():
            try:
                w.destroy()
            except Exception:
                pass
        self._tile_widgets.clear()

        windows = get_visible_windows()
        positions = self.config.get("tile_positions", {})
        cols = max(1, (self.sw - 80) // (self.TILE_W + 12))
        col_i = row_i = 0

        for hwnd, title, exe, is_min in windows:
            if "Desktop Canvas" in title:
                continue
            icon_text, name, grp, icon_bg = get_app_meta(exe, title)
            key = f"{exe}|{title[:40]}"
            if key in positions:
                x, y = positions[key]["x"], positions[key]["y"]
            else:
                x = 40 + col_i * (self.TILE_W + 12)
                y = 60 + row_i * (self.TILE_H + 12)
                col_i += 1
                if col_i >= cols:
                    col_i = 0
                    row_i += 1
            self._place_tile(key, x, y, hwnd, title, exe, name, icon_text, icon_bg, is_min, grp)

        self._cv_count.config(text=f"{len(self._tile_widgets)} windows")

    def _place_tile(self, key, x, y, hwnd, title, exe, name,
                    icon_text, icon_bg, is_min, group):
        bg = C["card"] if not is_min else "#1a1a28"
        fg = C["text"] if not is_min else C["dim"]
        gm = GROUP_META.get(group, ("?", C["dim"], "#1a1a22"))
        accent = gm[1] if not is_min else C["border"]

        shadow = tk.Frame(self._cv, bg="#08081a", width=self.TILE_W + 4,
                          height=self.TILE_H + 4, cursor="hand2")
        shadow.pack_propagate(False)
        tile = tk.Frame(shadow, bg=bg, width=self.TILE_W, height=self.TILE_H, cursor="hand2")
        tile.pack_propagate(False)
        tile.pack(padx=2, pady=2)

        tk.Frame(tile, bg=accent, height=3).pack(fill="x")
        icon_photo = _to_photo(render_icon(icon_text, icon_bg if not is_min else "#333344", 32))
        self._photo_refs.append(icon_photo)
        self._tile_photo_map.setdefault(key, []).append(icon_photo)
        ilbl = tk.Label(tile, image=icon_photo, bg=bg)
        ilbl.pack(pady=(4, 1))
        nlbl = tk.Label(tile, text=name[:9], font=("Segoe UI", 7), bg=bg, fg=fg)
        nlbl.pack()
        if is_min:
            tk.Label(tile, text="\u2012", font=("Segoe UI", 4), bg=bg, fg=C["dim"]).pack()

        win_id = self._cv.create_window(x, y, window=shadow, anchor="nw", tags=(f"tile_{key}",))
        self._tile_widgets[key] = shadow

        # Drag state
        ds = {"on": False, "sx": 0, "sy": 0, "ox": x, "oy": y, "moved": False}

        def press(e):
            if self.mode == "draw_zone":
                return
            ds.update(on=True, sx=e.x_root, sy=e.y_root, moved=False)
            coords = self._cv.coords(win_id)
            if coords:
                ds["ox"], ds["oy"] = coords[0], coords[1]
        def drag(e):
            if not ds["on"] or self.mode == "draw_zone":
                return
            dx, dy = e.x_root - ds["sx"], e.y_root - ds["sy"]
            if abs(dx) > 3 or abs(dy) > 3:
                ds["moved"] = True
            self._cv.coords(win_id, ds["ox"] + dx, ds["oy"] + dy)
        def release(e):
            if not ds["on"]:
                return
            ds["on"] = False
            if not ds["moved"]:
                focus_window(hwnd)
                return
            coords = self._cv.coords(win_id)
            if coords:
                nx, ny = int(coords[0]), int(coords[1])
                pos = self.config.setdefault("tile_positions", {})
                pos[key] = {"x": nx, "y": ny}
                # Check zone membership
                cx, cy = nx + self.TILE_W // 2, ny + self.TILE_H // 2
                for z in self.config.get("zones", []):
                    if z["x1"] <= cx <= z["x2"] and z["y1"] <= cy <= z["y2"]:
                        zname = z.get("name", "Zone")
                        if zname not in GROUP_META:
                            GROUP_META[zname] = (zname[0].upper(), z.get("colour", C["lavender"]), "#1a1a30")
                        self.config.setdefault("custom_groups", {})[exe] = zname
                        break
                save_canvas_config(self.config)
        def right(e):
            m = _styled_menu(self.root)
            m.add_command(label=f"Focus: {title[:40]}", command=lambda: focus_window(hwnd))
            m.add_command(label="Minimise", command=lambda: minimize_window(hwnd))
            m.tk_popup(e.x_root, e.y_root)
        def enter(e):
            shadow.configure(bg=accent)
            for ch in [tile] + list(tile.winfo_children()):
                try:
                    ch.configure(bg=C["card_hi"])
                except Exception:
                    pass
            _destroy_tooltip(self._tooltip_win)
            self._tooltip_win = _show_tooltip(self.root, e.x_root, e.y_root + 20, title)
        def leave(e):
            shadow.configure(bg="#08081a")
            for ch in [tile] + list(tile.winfo_children()):
                try:
                    ch.configure(bg=bg)
                except Exception:
                    pass
            _destroy_tooltip(self._tooltip_win)
            self._tooltip_win = None

        for w in [shadow, tile, ilbl, nlbl]:
            w.bind("<Button-1>", press)
            w.bind("<B1-Motion>", drag)
            w.bind("<ButtonRelease-1>", release)
            w.bind("<Button-3>", right)
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)

    # --- Zone drawing ---

    def _toggle_draw_mode(self):
        if self.mode == "draw_zone":
            self.mode = "normal"
            self._cv.config(cursor="arrow")
            self._set_mode_badge("NAVIGATE", C["green"])
        else:
            self.mode = "draw_zone"
            self._cv.config(cursor="crosshair")
            self._set_mode_badge("DRAW ZONE", C["yellow"])

    def _set_mode_badge(self, text, colour):
        self._mode_frame.config(bg=colour)
        self._mode_lbl.config(text=text, bg=colour, fg="#0d0d1e")

    def _cv_click(self, e):
        if self.mode != "draw_zone":
            return
        self._zone_start = (e.x, e.y)
        self._zone_rect_id = self._cv.create_rectangle(
            e.x, e.y, e.x, e.y, outline=C["yellow"], width=2, dash=(4, 3), tags=("drawing",))

    def _cv_drag(self, e):
        if self.mode != "draw_zone" or not self._zone_start:
            return
        self._cv.coords(self._zone_rect_id, *self._zone_start, e.x, e.y)

    def _cv_release(self, e):
        if self.mode != "draw_zone" or not self._zone_start:
            return
        sx, sy = self._zone_start
        self._zone_start = None
        try:
            if abs(e.x - sx) < self.ZONE_MIN or abs(e.y - sy) < self.ZONE_MIN:
                return
            x1, y1 = min(sx, e.x), min(sy, e.y)
            x2, y2 = max(sx, e.x), max(sy, e.y)
            zone_colours = [C["blue"], C["green"], C["peach"], C["mauve"],
                            C["teal"], C["pink"], C["sky"], C["yellow"]]
            zones = self.config.setdefault("zones", [])
            colour = zone_colours[len(zones) % len(zone_colours)]

            self.root.attributes("-topmost", False)
            try:
                name = simpledialog.askstring("Name This Zone",
                                              "Zone name (becomes a group):", parent=self.root)
            finally:
                self.root.attributes("-topmost", True)
            name = (name or "").strip() or f"Zone {len(zones) + 1}"

            zones.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                          "name": name, "colour": colour})
            if name not in GROUP_META:
                GROUP_META[name] = (name[0].upper(), colour, "#1a1a30")

            # Auto-group tiles already inside the zone
            cg = self.config.setdefault("custom_groups", {})
            for key, pos in self.config.get("tile_positions", {}).items():
                cx = pos["x"] + self.TILE_W // 2
                cy = pos["y"] + self.TILE_H // 2
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    cg[key.split("|")[0]] = name
            save_canvas_config(self.config)
            self._draw_zones()
        finally:
            if self._zone_rect_id:
                self._cv.delete(self._zone_rect_id)
                self._zone_rect_id = None
            self.mode = "normal"
            self._cv.config(cursor="arrow")
            self._set_mode_badge("NAVIGATE", C["green"])

    def _cv_right_click(self, e):
        for i, z in enumerate(self.config.get("zones", [])):
            if z["x1"] <= e.x <= z["x2"] and z["y1"] <= e.y <= z["y2"]:
                m = _styled_menu(self.root)
                m.add_command(label=f"Zone: {z['name']}", state="disabled")
                m.add_separator()
                m.add_command(label="Delete zone", command=lambda idx=i: self._delete_zone(idx))
                m.add_command(label="Rename zone", command=lambda idx=i: self._rename_zone(idx))
                m.tk_popup(e.x_root, e.y_root)
                return

    def _delete_zone(self, idx):
        zones = self.config.get("zones", [])
        if 0 <= idx < len(zones):
            zones.pop(idx)
            save_canvas_config(self.config)
            self._draw_zones()

    def _rename_zone(self, idx):
        zones = self.config.get("zones", [])
        if 0 <= idx < len(zones):
            self.root.attributes("-topmost", False)
            try:
                name = simpledialog.askstring("Rename Zone", "New name:",
                                              initialvalue=zones[idx]["name"], parent=self.root)
            finally:
                self.root.attributes("-topmost", True)
            if name and name.strip():
                zones[idx]["name"] = name.strip()
                save_canvas_config(self.config)
                self._draw_zones()

    def _clear_zones(self):
        self.config["zones"] = []
        save_canvas_config(self.config)
        self._draw_zones()

    def _reset_positions(self):
        self.config["tile_positions"] = {}
        save_canvas_config(self.config)
        self._populate()

    # --- Soft refresh (add new / remove gone, don't move existing) ---

    def _start_refresh(self):
        def _loop():
            while self._alive:
                time.sleep(CANVAS_REFRESH)
                if not self.root or not self._alive:
                    break
                try:
                    self.root.after(0, self._soft_refresh)
                except Exception:
                    break
        threading.Thread(target=_loop, daemon=True).start()

    def _soft_refresh(self):
        windows = get_visible_windows()
        current_keys = set()
        for hwnd, title, exe, is_min in windows:
            if "Desktop Canvas" in title:
                continue
            key = f"{exe}|{title[:40]}"
            current_keys.add(key)
            if key not in self._tile_widgets:
                icon_text, name, grp, icon_bg = get_app_meta(exe, title)
                pos = self.config.get("tile_positions", {})
                if key in pos:
                    x, y = pos[key]["x"], pos[key]["y"]
                else:
                    n = len(self._tile_widgets)
                    x, y = 40 + (n % 12) * 92, 60 + (n // 12) * 92
                self._place_tile(key, x, y, hwnd, title, exe, name, icon_text, icon_bg, is_min, grp)

        for key in set(self._tile_widgets) - current_keys:
            try:
                self._cv.delete(f"tile_{key}")
            except Exception:
                pass
            try:
                self._tile_widgets[key].destroy()
            except Exception:
                pass
            del self._tile_widgets[key]
            self._tile_photo_map.pop(key, None)

        self._cv_count.config(text=f"{len(self._tile_widgets)} windows")

    # --- Passthrough (ghost mode) ---

    def _toggle_passthrough(self):
        if self._passthrough:
            self._exit_passthrough()
        else:
            self._enter_passthrough()

    def _enter_passthrough(self):
        if not self._hwnd or not self.root:
            return
        if not win32gui.IsWindow(self._hwnd):
            self._hwnd = self._find_hwnd()
            if not self._hwnd:
                return
        self._passthrough = True
        self.mode = "passthrough"
        user32 = ctypes.windll.user32
        ex = user32.GetWindowLongW(self._hwnd, self.GWL_EXSTYLE)
        user32.SetWindowLongW(self._hwnd, self.GWL_EXSTYLE,
                              ex | self.WS_EX_TRANSPARENT | self.WS_EX_LAYERED)
        user32.SetLayeredWindowAttributes(self._hwnd, 0, 25, 2)  # ~10% opacity
        try:
            self.root.attributes("-alpha", self.ALPHA_PASSTHROUGH)
        except Exception:
            pass
        self._set_mode_badge("PASSTHROUGH", C["sky"])
        self._pt_border.config(bg=C["sky"])
        self._pt_btn.config(text="\u25CF  Passthrough ON", fg="#0d0d1e", bg=C["sky"])

    def _exit_passthrough(self):
        if not self._hwnd or not self.root:
            return
        if not win32gui.IsWindow(self._hwnd):
            self._hwnd = self._find_hwnd()
            if not self._hwnd:
                return
        self._passthrough = False
        self.mode = "normal"
        user32 = ctypes.windll.user32
        ex = user32.GetWindowLongW(self._hwnd, self.GWL_EXSTYLE)
        user32.SetWindowLongW(self._hwnd, self.GWL_EXSTYLE, ex & ~self.WS_EX_TRANSPARENT)
        user32.SetLayeredWindowAttributes(self._hwnd, 0, 224, 2)  # ~88% opacity
        try:
            self.root.attributes("-alpha", self.ALPHA_NORMAL)
        except Exception:
            pass
        self.root.lift()
        self.root.focus_force()
        self._set_mode_badge("NAVIGATE", C["green"])
        self._pt_border.config(bg=C["sky"])
        self._pt_btn.config(text="\u25CB  Passthrough", fg=C["sky"], bg="#0d0d1e")

    def _start_focus_monitor(self):
        """Auto-exit passthrough when canvas regains focus."""
        def _loop():
            while self._alive:
                time.sleep(0.25)
                if not self.root or not self._alive or not self._passthrough:
                    continue
                try:
                    fg = win32gui.GetForegroundWindow()
                    if (self._hwnd and fg == self._hwnd) or \
                       "Desktop Canvas" in win32gui.GetWindowText(fg):
                        self.root.after(0, self._exit_passthrough)
                except Exception:
                    pass
        threading.Thread(target=_loop, daemon=True).start()

    def refocus(self):
        """Called from tray to bring canvas back from passthrough."""
        if self.root:
            if self._passthrough:
                self.root.after(0, self._exit_passthrough)
            try:
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass


# ────────────────────────────────────────────────────────────────
# 8. TRAY & MAIN
# ────────────────────────────────────────────────────────────────

def _create_tray_image() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, size - 2, size - 2], radius=12, fill=(137, 180, 250))
    try:
        f = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        f = ImageFont.load_default()
    d.text((size // 2, size // 2), "TL", fill=(15, 15, 26), font=f, anchor="mm")
    return img


def main():
    tiles = TilesWindow()
    canvas = DesktopCanvas()

    def show_tiles(icon, item):
        threading.Thread(target=tiles.show, daemon=True).start()

    def show_canvas(icon, item):
        threading.Thread(target=canvas.show, daemon=True).start()

    def refocus_canvas(icon, item):
        canvas.refocus()

    def quit_app(icon, item):
        for obj in (tiles, canvas):
            obj._alive = False
            try:
                if obj.root:
                    obj.root.destroy()
            except Exception:
                pass
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Show Tiles", show_tiles, default=True),
        pystray.MenuItem("Desktop Canvas", show_canvas),
        pystray.MenuItem("Refocus Canvas", refocus_canvas),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )
    icon = pystray.Icon("niggly_tiles", _create_tray_image(),
                        f"Window Tiles v{__version__}", menu)
    threading.Timer(0.5, lambda: threading.Thread(target=tiles.show, daemon=True).start()).start()
    icon.run()


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("tiles.py")
    main()
