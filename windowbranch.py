"""
Lawrence: Move In — Branch v1.0.0
Full-screen branch overlay: scans all open windows + browser tabs.
Draws a 2D pannable/zoomable radial tree with a human-heartbeat
oscillator cycling through nodes. Click any node → jump there.
Zones overlay: shows windows mapped to actual screen positions.
Hotkey: Ctrl+Alt+B  |  Tray icon  |  Auto-shows on idle (optional)
"""
__version__ = "1.0.0"
import selfclean; selfclean.ensure_single("windowbranch.py")

import ctypes, json, math, os, random, sys, threading, time
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass, field
from typing import List, Optional, Any
from pathlib import Path

import win32gui, win32con, win32process, win32api
import psutil, pystray, keyboard
import uiautomation as uia
from PIL import Image as PILImage, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / "windowbranch_state.json"

# ── Colours ───────────────────────────────────────────────────────────────────
BG      = "#0d1117"
BG2     = "#161b22"
BG3     = "#21262d"
FG      = "#e6edf3"
FG_DIM  = "#484f58"
BLUE    = "#79c0ff"
GREEN   = "#7ee787"
YELLOW  = "#e3b341"
PURPLE  = "#d2a8ff"
RED     = "#ff7b72"
ORANGE  = "#ffa657"
TEAL    = "#76e3ea"
EDGE    = "#30363d"
ACTIVE  = "#7ee787"
GLOW    = "#56d364"

APP_COLORS = {
    "chrome":     "#4285f4", "msedge":  "#0078d7", "firefox": "#ff6611",
    "code":       "#007acc", "notepad": "#ffe082", "explorer":"#5c9bd6",
    "telegram":   "#2ca5e0", "discord": "#7289da", "spotify": "#1db954",
    "outlook":    "#0072c6", "excel":   "#1d6f42", "word":    "#2b579a",
    "teams":      "#6264a7", "slack":   "#4a154b", "python":  "#ffd43b",
    "cmd":        "#cccccc", "powershell":"#012456","windowbot":"#89b4fa",
    "niggly":     "#f9e2af", "kidlin":  "#cba6f7", "hub":     "#94e2d5",
}

def _app_color(exe: str) -> str:
    e = exe.lower().replace(".exe", "")
    for k, v in APP_COLORS.items():
        if k in e: return v
    return "#58a6ff"

BROWSER_EXES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}

# ── Idle detection ────────────────────────────────────────────────────────────
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def idle_ms() -> int:
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    return ctypes.windll.kernel32.GetTickCount() - lii.dwTime

# ── State ─────────────────────────────────────────────────────────────────────
def _load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"auto_idle_minutes": 0, "osc_base_ms": 4000,
            "osc_depth": 0.45, "osc_jitter": 0.20, "osc_speed": 0.25}

def _save_state(s: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except: pass

# ── Window node ───────────────────────────────────────────────────────────────
@dataclass
class WNode:
    hwnd:     int
    title:    str
    exe:      str
    color:    str
    is_tab:   bool = False
    tab_idx:  int  = -1
    uia_ref:  Any  = None
    parent_node: Optional['WNode'] = None
    children: List['WNode'] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0

# ── Window scanning ───────────────────────────────────────────────────────────
_SKIP_TITLES = {"Program Manager", "Default IME", "MSCTFIME UI", ""}
_SKIP_EXES   = {"searchapp.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe"}

def scan_windows() -> List[WNode]:
    nodes: List[WNode] = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd): return True
        t = win32gui.GetWindowText(hwnd)
        if not t or t in _SKIP_TITLES or len(t) < 2: return True
        if any(x in t for x in ("Branch","BotPrompt","ScreenRouter","Bot Prompt")): return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            exe = psutil.Process(pid).name()
        except:
            exe = "unknown.exe"
        if exe.lower() in _SKIP_EXES: return True

        node = WNode(hwnd=hwnd, title=t[:64], exe=exe, color=_app_color(exe))

        # Browser tab enumeration via uiautomation
        if exe.lower() in BROWSER_EXES:
            try:
                win_ctl = uia.ControlFromHandle(hwnd)
                # Walk looking for TabControl or list of Tab items
                def _find_tabs(ctl, depth=0):
                    if depth > 6: return []
                    found = []
                    ct = ctl.ControlTypeName
                    if ct in ("TabControl",):
                        for c in ctl.GetChildren():
                            if c.ControlTypeName in ("TabItem", "ListItem"):
                                found.append(c)
                    else:
                        for c in ctl.GetChildren():
                            found.extend(_find_tabs(c, depth+1))
                    return found

                tab_items = _find_tabs(win_ctl)
                for i, tab in enumerate(tab_items[:24]):
                    name = tab.Name.strip()[:64] if tab.Name else f"Tab {i+1}"
                    if name:
                        tnode = WNode(
                            hwnd=hwnd, title=name, exe=exe, color=node.color,
                            is_tab=True, tab_idx=i, uia_ref=tab, parent_node=node
                        )
                        node.children.append(tnode)
            except:
                pass

        nodes.append(node)
        return True

    try: win32gui.EnumWindows(_cb, None)
    except: pass
    return nodes

def flatten(nodes: List[WNode]) -> List[WNode]:
    result = []
    for n in nodes:
        result.append(n)
        result.extend(n.children)
    return result

# ── Layout ────────────────────────────────────────────────────────────────────
def layout_radial(nodes: List[WNode], cx: float, cy: float):
    """Radial fan: group by exe, each group fans at its angle ring."""
    if not nodes: return

    groups: dict[str, List[WNode]] = {}
    for n in nodes:
        groups.setdefault(n.exe, []).append(n)

    group_list = list(groups.values())
    n_groups   = len(group_list)

    for gi, gnodes in enumerate(group_list):
        base_angle = (2 * math.pi * gi / n_groups) - math.pi / 2
        n_in_group = len(gnodes)
        spread = 0.55 if n_in_group > 1 else 0.0

        for ni, node in enumerate(gnodes):
            fan = spread * ((ni / max(1, n_in_group - 1)) - 0.5)
            angle = base_angle + fan
            r = 300 + (ni % 3) * 30
            node.x = cx + r * math.cos(angle)
            node.y = cy + r * math.sin(angle)

            # Children (tabs) fan outward
            n_tabs = len(node.children)
            for ti, tab in enumerate(node.children):
                tfan = 0.3 * ((ti / max(1, n_tabs - 1)) - 0.5)
                tangle = angle + tfan
                tab.x = cx + (r + 170) * math.cos(tangle)
                tab.y = cy + (r + 170) * math.sin(tangle)

# ── Oscillator ────────────────────────────────────────────────────────────────
class Oscillator:
    def __init__(self, state: dict):
        self.base_ms   = state.get("osc_base_ms",  4000)
        self.depth     = state.get("osc_depth",    0.45)
        self.jitter    = state.get("osc_jitter",   0.20)
        self.osc_speed = state.get("osc_speed",    0.25)
        self._phase    = random.uniform(0, 2 * math.pi)
        self._running  = False
        self._cb       = None

    def next_ms(self) -> int:
        self._phase += self.osc_speed + random.gauss(0, 0.04)
        mod   = math.sin(self._phase) * self.depth
        jit   = random.gauss(0, self.jitter * 0.5)
        ms    = self.base_ms * (1.0 + mod + jit)
        return max(400, int(ms))

    def wave_preview(self, n=80) -> List[float]:
        """Normalised 0-1 values for the next n beats."""
        phase = self._phase
        out   = []
        for _ in range(n):
            phase += self.osc_speed
            out.append(0.5 + 0.5 * math.sin(phase) * self.depth)
        return out

    def start(self, cb):
        self._cb = cb; self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            time.sleep(self.next_ms() / 1000.0)
            if self._running and self._cb:
                self._cb()

    def to_state(self) -> dict:
        return {"osc_base_ms": self.base_ms, "osc_depth": self.depth,
                "osc_jitter": self.jitter,   "osc_speed": self.osc_speed}

# ── Oscillator wave display ───────────────────────────────────────────────────
class WaveBar(tk.Canvas):
    def __init__(self, parent, osc: Oscillator, **kw):
        super().__init__(parent, bg=BG, highlightthickness=0, height=28, **kw)
        self._osc = osc
        self._animate()

    def _animate(self):
        self.delete("all")
        w = max(self.winfo_width(), 10)
        vals = self._osc.wave_preview(w // 3)
        pts  = []
        for i, v in enumerate(vals):
            pts.extend([i * 3, int((1 - v) * 22 + 3)])
        if len(pts) >= 4:
            self.create_line(*pts, fill=BLUE, width=1, smooth=True)
        # current beat marker
        self.create_line(0, 14, 8, 14, fill=GLOW, width=2)
        self.after(100, self._animate)

# ── Branch canvas ─────────────────────────────────────────────────────────────
NW, NH = 154, 42

class BranchCanvas(tk.Canvas):
    def __init__(self, parent, nodes: List[WNode], on_select, **kw):
        super().__init__(parent, bg=BG, highlightthickness=0, **kw)
        self._nodes     = nodes
        self._flat      = flatten(nodes)
        self._on_select = on_select
        self._active    = 0
        self._ox = 0.0; self._oy = 0.0; self._sc = 1.0
        self._drag      = None
        self._items: dict[int, WNode] = {}

        self.bind("<ButtonPress-1>",  self._click)
        self.bind("<ButtonPress-3>",  self._pan_start)
        self.bind("<B3-Motion>",      self._pan_move)
        self.bind("<ButtonPress-2>",  self._pan_start)
        self.bind("<B2-Motion>",      self._pan_move)
        self.bind("<MouseWheel>",     self._zoom)
        self.bind("<Configure>",      lambda e: self._draw())
        self._draw()

    def set_active(self, idx: int):
        self._active = idx % max(1, len(self._flat))
        self._draw()

    def get_active_node(self) -> Optional[WNode]:
        if not self._flat: return None
        return self._flat[self._active % len(self._flat)]

    def _wx(self, x): return x * self._sc + self._ox
    def _wy(self, y): return y * self._sc + self._oy

    def _draw(self):
        self.delete("all")
        self._items.clear()
        w = self.winfo_width()  or 900
        h = self.winfo_height() or 600
        if not self._flat:
            self.create_text(w//2, h//2, text="No windows found",
                             fill=FG_DIM, font=("Segoe UI", 16))
            return

        active_node = self._flat[self._active % len(self._flat)]

        # Edges: parent → child (tabs)
        for node in self._nodes:
            for tab in node.children:
                x1, y1 = self._wx(node.x), self._wy(node.y)
                x2, y2 = self._wx(tab.x),  self._wy(tab.y)
                mx = (x1 + x2) / 2
                self.create_line(x1, y1, mx, y1, mx, y2, x2, y2,
                                 fill=EDGE, width=1, smooth=True, dash=(3, 4))

        # Nodes
        for node in self._flat:
            x  = self._wx(node.x)
            y  = self._wy(node.y)
            hw = NW / 2 * self._sc
            hh = NH / 2 * self._sc
            is_active = (node is active_node)

            # Glow rings
            if is_active:
                for g in [12, 8, 4]:
                    self.create_rectangle(
                        x-hw-g, y-hh-g, x+hw+g, y+hh+g,
                        fill="", outline=GLOW,
                        width=1, stipple="gray25")

            # Node box
            fill    = node.color if is_active else BG2
            outline = GLOW if is_active else node.color
            lw      = 2 if is_active else 1
            iid = self.create_rectangle(
                x-hw, y-hh, x+hw, y+hh,
                fill=fill, outline=outline, width=lw, tags="node")
            self._items[iid] = node

            # Tab indicator pill
            if node.is_tab:
                self.create_oval(x-hw+3, y-hh+3, x-hw+10, y-hh+10,
                                 fill=node.color, outline="")

            # Title
            chars = max(5, int(hw * 1.7 / 7))
            title = (node.title[:chars-1] + "…") if len(node.title) > chars else node.title
            fg_t  = BG if is_active else FG
            t1 = self.create_text(x, y - 6, text=title,
                                  fill=fg_t, font=("Segoe UI", 8, "bold"),
                                  width=hw * 1.8, anchor="center", tags="node")
            self._items[t1] = node

            # Exe
            t2 = self.create_text(x, y + 10,
                                  text=node.exe.replace(".exe","")[:18],
                                  fill=(BG if is_active else FG_DIM),
                                  font=("Segoe UI", 7),
                                  anchor="center", tags="node")
            self._items[t2] = node

    def _click(self, event):
        for iid in self.find_closest(event.x, event.y, halo=6):
            if iid in self._items:
                self._on_select(self._items[iid])
                return

    def _pan_start(self, e):
        self._drag = (e.x, e.y, self._ox, self._oy)

    def _pan_move(self, e):
        if not self._drag: return
        sx, sy, ox, oy = self._drag
        self._ox = ox + e.x - sx
        self._oy = oy + e.y - sy
        self._draw()

    def _zoom(self, e):
        f = 1.1 if e.delta > 0 else 0.9
        self._ox = e.x + (self._ox - e.x) * f
        self._oy = e.y + (self._oy - e.y) * f
        self._sc = max(0.15, min(4.0, self._sc * f))
        self._draw()

# ── Zones overlay ─────────────────────────────────────────────────────────────
class ZonesOverlay:
    def __init__(self, parent, nodes: List[WNode], on_select, on_close):
        self._on_close = on_close
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        W, H = 560, 360
        self.win = tk.Toplevel(parent)
        self.win.configure(bg=BG)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.94)
        self.win.geometry(f"{W}x{H}+{sw//2-W//2}+{sh//2-H//2}")
        self.win.title("Zones")
        self.win.resizable(True, True)

        tk.Label(self.win, text="Zones — windows by screen position",
                 font=("Segoe UI", 8, "bold"), fg=BLUE, bg=BG).pack(pady=(6,0))

        c = tk.Canvas(self.win, bg=BG2, highlightthickness=0)
        c.pack(fill="both", expand=True, padx=10, pady=4)
        self._items: dict[int, WNode] = {}

        def _draw(event=None):
            c.delete("all")
            cw = c.winfo_width()  or W - 20
            ch = c.winfo_height() or H - 70
            m  = 10
            # Screen outline
            c.create_rectangle(m, m, cw-m, ch-m, outline=FG_DIM, width=1)

            for node in nodes:
                try:
                    r   = win32gui.GetWindowRect(node.hwnd)
                    nx  = m + int((r[0] / sw) * (cw - 2*m))
                    ny  = m + int((r[1] / sh) * (ch - 2*m))
                    nw_ = max(18, int(((r[2]-r[0]) / sw) * (cw - 2*m)))
                    nh_ = max(12, int(((r[3]-r[1]) / sh) * (ch - 2*m)))
                    bid = c.create_rectangle(nx, ny, nx+nw_, ny+nh_,
                                             fill=node.color+"55",
                                             outline=node.color, width=1)
                    tid = c.create_text(nx+3, ny+2,
                                        text=node.title[:20],
                                        fill=FG, font=("Segoe UI", 6),
                                        anchor="nw")
                    self._items[bid] = node
                    self._items[tid] = node
                except: pass

        c.bind("<Configure>", _draw)
        c.bind("<Button-1>", lambda e: self._click(c, e, on_select))

        btns = tk.Frame(self.win, bg=BG)
        btns.pack(fill="x", padx=10, pady=(0,6))
        tk.Button(btns, text="Refresh", font=("Segoe UI", 7),
                  fg=GREEN, bg=BG2, relief="flat", padx=8,
                  command=lambda: (_draw(), None)).pack(side="left")
        tk.Button(btns, text="Close", font=("Segoe UI", 7),
                  fg=RED, bg=BG2, relief="flat", padx=8,
                  command=self._close).pack(side="right")
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        self.win.after(100, _draw)

    def _click(self, c, e, on_select):
        for iid in c.find_closest(e.x, e.y, halo=8):
            if iid in self._items:
                on_select(self._items[iid])
                return

    def _close(self):
        try: self.win.destroy()
        except: pass
        self._on_close()

# ── Settings panel ────────────────────────────────────────────────────────────
class SettingsPanel:
    def __init__(self, parent, osc: Oscillator, state: dict,
                 on_rescan, on_close):
        self._osc = osc
        self._on_close = on_close
        sw = parent.winfo_screenwidth()
        self.win = tk.Toplevel(parent)
        self.win.configure(bg=BG)
        self.win.attributes("-topmost", True)
        self.win.title("Branch Settings")
        self.win.resizable(False, False)
        self.win.geometry(f"310x400+{sw-330}+60")

        tk.Label(self.win, text="Branch  ·  Oscillator",
                 font=("Consolas", 10, "bold"), fg=BLUE, bg=BG).pack(pady=(10,2))

        def _slider(label, attr, from_, to):
            f = tk.Frame(self.win, bg=BG)
            f.pack(fill="x", padx=16, pady=3)
            tk.Label(f, text=label, font=("Segoe UI", 8), fg=FG,
                     bg=BG, width=20, anchor="w").pack(side="left")
            val_lbl = tk.Label(f, text=f"{getattr(osc, attr):.2f}",
                               font=("Consolas", 8), fg=YELLOW, bg=BG, width=5)
            val_lbl.pack(side="right")
            def _set(v, a=attr, lbl=val_lbl):
                v = float(v)
                if a == "base_ms": v = int(v * 1000)
                setattr(osc, a, v)
                lbl.config(text=f"{float(v):.2f}" if a != "base_ms"
                           else f"{v/1000:.1f}s")
            s = ttk.Scale(f, from_=from_, to=to, orient="horizontal",
                          length=130, command=_set)
            s.set(osc.base_ms / 1000 if attr == "base_ms" else getattr(osc, attr))
            s.pack(side="right", padx=4)

        _slider("Base interval (s)", "base_ms",   1.0, 20.0)
        _slider("Depth (oscillation)","depth",     0.0,  1.0)
        _slider("Jitter (randomness)", "jitter",   0.0,  1.0)
        _slider("Osc. speed",          "osc_speed",0.05, 1.2)

        tk.Label(self.win, text="Waveform preview (upcoming timing):",
                 font=("Segoe UI", 7), fg=FG_DIM, bg=BG).pack(pady=(8,0), padx=16, anchor="w")
        WaveBar(self.win, osc).pack(fill="x", padx=16, pady=4)

        # Idle auto-show
        tk.Label(self.win, text="Auto-show after idle (0 = off):",
                 font=("Segoe UI", 7), fg=FG_DIM, bg=BG).pack(padx=16, anchor="w")
        idle_f = tk.Frame(self.win, bg=BG)
        idle_f.pack(fill="x", padx=16, pady=2)
        idle_var = tk.IntVar(value=state.get("auto_idle_minutes", 0))
        tk.Spinbox(idle_f, from_=0, to=60, textvariable=idle_var,
                   width=4, font=("Segoe UI", 9), bg=BG2, fg=FG,
                   insertbackground=BLUE,
                   command=lambda: state.update({"auto_idle_minutes": idle_var.get()})
                   ).pack(side="left")
        tk.Label(idle_f, text=" minutes", font=("Segoe UI", 8),
                 fg=FG_DIM, bg=BG).pack(side="left")

        tk.Label(self.win, text="Hotkey: Ctrl+Alt+B to show/hide",
                 font=("Segoe UI", 7), fg=FG_DIM, bg=BG).pack(padx=16, anchor="w", pady=4)

        btn_r = tk.Frame(self.win, bg=BG)
        btn_r.pack(fill="x", padx=16, pady=8)
        tk.Button(btn_r, text="Re-scan", font=("Segoe UI", 8),
                  fg=BG, bg=GREEN, relief="flat", padx=10, pady=3,
                  command=on_rescan).pack(side="left")
        tk.Button(btn_r, text="Close", font=("Segoe UI", 8),
                  fg=RED, bg=BG2, relief="flat", padx=10, pady=3,
                  command=self._close).pack(side="right")
        self.win.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        try: self.win.destroy()
        except: pass
        self._on_close()

# ── Focus helper ──────────────────────────────────────────────────────────────
def focus_node(node: WNode):
    def _go():
        try:
            hwnd = node.hwnd
            if not win32gui.IsWindow(hwnd): return
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)

            if node.is_tab:
                time.sleep(0.15)
                if node.uia_ref:
                    try: node.uia_ref.Click()
                    except: pass
                elif node.tab_idx >= 0:
                    # Ctrl+1..9 fallback for first 9 tabs
                    if node.tab_idx < 8:
                        win32api.keybd_event(0x11, 0, 0, 0)
                        win32api.keybd_event(0x31 + node.tab_idx, 0, 0, 0)
                        win32api.keybd_event(0x31 + node.tab_idx, 0, 2, 0)
                        win32api.keybd_event(0x11, 0, 2, 0)
        except: pass
    threading.Thread(target=_go, daemon=True).start()

# ── Branch overlay window ─────────────────────────────────────────────────────
class BranchOverlay:
    def __init__(self, root: tk.Tk, osc: Oscillator, state: dict, on_close):
        self._root     = root
        self._osc      = osc
        self._state    = state
        self._on_close = on_close
        self._settings_open = False
        self._zones_open    = False
        self._nodes: List[WNode] = []
        self._bc: Optional[BranchCanvas] = None

        self.win = tk.Toplevel(root)
        self.win.configure(bg=BG)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.94)
        self.win.attributes("-fullscreen", True)
        self.win.title("Branch")
        self.win.focus_force()

        self.win.bind("<Escape>", lambda e: self._close())
        self.win.bind("<F5>",     lambda e: self._rescan())
        self.win.bind("<space>",  lambda e: self._advance())
        self.win.bind("<Return>", lambda e: self._go_active())

        self._build_chrome()
        self._rescan()
        self._osc.start(lambda: root.after(0, self._advance))

    def _build_chrome(self):
        # Top bar
        bar = tk.Frame(self.win, bg=BG2, pady=5)
        bar.pack(fill="x", side="top")
        tk.Label(bar, text="Branch", font=("Consolas", 11, "bold"),
                 fg=BLUE, bg=BG2).pack(side="left", padx=12)
        self._status_lbl = tk.Label(bar, text="Scanning…",
                                     font=("Segoe UI", 8), fg=FG_DIM, bg=BG2)
        self._status_lbl.pack(side="left", padx=4)

        for txt, cmd, col in [
            ("✕ Close (Esc)", self._close,      RED),
            ("⊞ Zones",       self._open_zones, PURPLE),
            ("⚙ Settings",    self._open_settings, BLUE),
            ("↻ Scan (F5)",   self._rescan,     GREEN),
        ]:
            tk.Button(bar, text=txt, font=("Segoe UI", 8),
                      fg=col, bg=BG2, activebackground=BG3,
                      activeforeground=col, relief="flat",
                      padx=10, pady=2, cursor="hand2",
                      command=cmd).pack(side="right", padx=1)

        # Canvas area (filled between bar and hint)
        self._canvas_host = tk.Frame(self.win, bg=BG)
        self._canvas_host.pack(fill="both", expand=True)

        # Bottom hint
        hint = tk.Frame(self.win, bg=BG2, pady=3)
        hint.pack(fill="x", side="bottom")
        tk.Label(hint,
                 text="Click node → go there  ·  Space / Enter → go to highlighted  ·  "
                      "Scroll = zoom  ·  Right-drag = pan  ·  F5 = rescan  ·  Esc = close",
                 font=("Segoe UI", 7), fg=FG_DIM, bg=BG2).pack()

    def _rescan(self):
        self._status_lbl.config(text="Scanning…", fg=YELLOW)

        def _work():
            nodes = scan_windows()
            sw    = self.win.winfo_screenwidth()
            sh    = self.win.winfo_screenheight()
            layout_radial(nodes, sw / 2, sh / 2)
            self._root.after(0, lambda: self._apply(nodes))

        threading.Thread(target=_work, daemon=True).start()

    def _apply(self, nodes: List[WNode]):
        self._nodes = nodes
        flat  = flatten(nodes)
        tabs  = sum(len(n.children) for n in nodes)
        total = len(flat)
        self._status_lbl.config(
            text=f"{len(nodes)} windows · {tabs} tabs · {total} nodes",
            fg=FG_DIM)

        if self._bc:
            self._bc.destroy()
        self._bc = BranchCanvas(self._canvas_host, nodes,
                                on_select=self._select)
        self._bc.pack(fill="both", expand=True)

    def _advance(self):
        if self._bc:
            self._bc.set_active(self._bc._active + 1)

    def _go_active(self):
        if self._bc:
            node = self._bc.get_active_node()
            if node:
                self._select(node)

    def _select(self, node: WNode):
        self._close()
        focus_node(node)

    def _open_settings(self):
        if self._settings_open: return
        self._settings_open = True
        SettingsPanel(self.win, self._osc, self._state,
                      on_rescan=self._rescan,
                      on_close=lambda: setattr(self, '_settings_open', False))

    def _open_zones(self):
        if self._zones_open: return
        self._zones_open = True
        ZonesOverlay(self.win, self._nodes,
                     on_select=self._select,
                     on_close=lambda: setattr(self, '_zones_open', False))

    def _close(self):
        self._osc.stop()
        try: self.win.destroy()
        except: pass
        self._on_close()

# ── App ────────────────────────────────────────────────────────────────────────
class BranchApp:
    def __init__(self):
        self.root      = tk.Tk()
        self.root.withdraw()
        self._state    = _load_state()
        self._osc      = Oscillator(self._state)
        self._overlay: Optional[BranchOverlay] = None
        self._tray_icon = None

        # Global hotkey
        try:
            keyboard.add_hotkey("ctrl+alt+b", lambda: self.root.after(0, self.toggle))
        except: pass

        self._build_tray()
        self.root.after(3000, self._idle_check)

    def toggle(self):
        if self._overlay:
            self._overlay._close()
        else:
            self._show()

    def _show(self):
        if self._overlay: return
        self._overlay = BranchOverlay(
            self.root, self._osc, self._state,
            on_close=self._overlay_closed)

    def _overlay_closed(self):
        self._overlay = None
        self._osc = Oscillator(self._state)   # fresh oscillator for next show
        self._state.update(self._osc.to_state())

    def _idle_check(self):
        idle_mins = self._state.get("auto_idle_minutes", 0)
        if idle_mins > 0 and not self._overlay:
            if idle_ms() >= idle_mins * 60_000:
                self._show()
        self.root.after(10_000, self._idle_check)

    def _build_tray(self):
        img = PILImage.new("RGBA", (64, 64), (0,0,0,0))
        d   = ImageDraw.Draw(img)
        # Branch icon: root dot + 4 branch lines + leaf dots
        cx, cy = 32, 12
        d.ellipse([cx-5, cy-5, cx+5, cy+5], fill=BLUE)
        branches = [(16, 30, GREEN), (48, 30, PURPLE)]
        for bx, by, col in branches:
            d.line([cx, cy+5, bx, by], fill=col, width=2)
            d.ellipse([bx-5,by-5,bx+5,by+5], fill=col)
            d.line([bx-10, by+14, bx, by+5], fill=col, width=1)
            d.line([bx+10, by+14, bx, by+5], fill=col, width=1)
            d.ellipse([bx-15,by+10,bx-5,by+20], fill=col)
            d.ellipse([bx+5, by+10,bx+15,by+20], fill=col)

        menu = pystray.Menu(
            pystray.MenuItem(f"Branch v{__version__}", None, enabled=False),
            pystray.MenuItem("Ctrl+Alt+B to toggle", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show Branch",
                             lambda: self.root.after(0, self._show)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self._tray_icon = pystray.Icon("branch", img,
                                       f"Branch v{__version__}", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _quit(self, *_):
        self._state.update(self._osc.to_state())
        _save_state(self._state)
        try: self._tray_icon.stop()
        except: pass
        self.root.after(0, self.root.destroy)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    BranchApp().run()
