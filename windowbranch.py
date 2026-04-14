"""
Lawrence: Move In — Branch v1.4.0
Full-screen branch overlay: scans all open windows + browser tabs.
Draws a 2D pannable/zoomable radial tree with a human-heartbeat
oscillator cycling through nodes. Click any node → jump there.
Zones overlay: shows windows mapped to actual screen positions.
Playground: full-screen bookmark board with coloured zones, shaped
  nodes, favicon loading, pan/zoom, edit mode drag & reshape.
  Laurence preset pre-loaded with 10 zones and 40 bookmarks.
Hotkey: Ctrl+Alt+B  |  Tray icon  |  Auto-shows on idle (optional)
"""
__version__ = "1.4.0"
import selfclean; selfclean.ensure_single("windowbranch.py")

import ctypes, json, math, os, random, sys, threading, time, webbrowser
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
    children:   List['WNode'] = field(default_factory=list)
    x:          float = 0.0
    y:          float = 0.0
    preset_url: str   = ""      # non-empty → bookmark node, no real hwnd yet
    zone_label: str   = ""      # zone name shown under preset nodes

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
            is_preset = bool(node.preset_url)

            # Glow rings (active node)
            if is_active:
                glow_col = PURPLE if is_preset else GLOW
                for g in [12, 8, 4]:
                    self.create_rectangle(
                        x-hw-g, y-hh-g, x+hw+g, y+hh+g,
                        fill="", outline=glow_col,
                        width=1, stipple="gray25")

            # Node box
            if is_preset:
                # Bookmark node: dashed outline, dim fill, pill shape (rounded ends)
                fill    = (node.color + "44") if is_active else BG
                outline = node.color if is_active else (node.color + "88")
                lw      = 2 if is_active else 1
                dash_   = () if is_active else (5, 3)
                # Draw with rounded rectangle (polygon smooth)
                r   = min(10, hh * 0.45)
                pts = [x-hw+r, y-hh, x+hw-r, y-hh,
                       x+hw, y-hh+r, x+hw, y+hh-r,
                       x+hw-r, y+hh, x-hw+r, y+hh,
                       x-hw, y+hh-r, x-hw, y-hh+r]
                iid = self.create_polygon(*pts, smooth=True,
                                          fill=fill, outline=outline,
                                          width=lw, dash=dash_, tags="node")
                self._items[iid] = node
                # ⊕ open icon top-right
                self.create_text(x + hw - 7, y - hh + 5,
                                  text="⊕", fill=node.color,
                                  font=("Segoe UI", 7), anchor="center")
            else:
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
            if is_active:
                fg_t = BG if not is_preset else node.color
            else:
                fg_t = (node.color + "cc") if is_preset else FG
            font_t = ("Segoe UI", 8, "bold") if (is_active or is_preset) else ("Segoe UI", 8)
            t1 = self.create_text(x, y - 6, text=title,
                                  fill=fg_t, font=font_t,
                                  width=hw * 1.8, anchor="center", tags="node")
            self._items[t1] = node

            # Sub-label: exe for real nodes, zone for preset nodes
            sub = node.zone_label if is_preset else node.exe.replace(".exe","")[:18]
            t2 = self.create_text(x, y + 10,
                                  text=sub,
                                  fill=(BG if (is_active and not is_preset) else FG_DIM),
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
        self.win.attributes("-alpha", 0.10)
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
    """Focus a real window. Does NOT open preset URLs (use activate_node for that)."""
    if node.preset_url: return
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
                    if node.tab_idx < 8:
                        win32api.keybd_event(0x11, 0, 0, 0)
                        win32api.keybd_event(0x31 + node.tab_idx, 0, 0, 0)
                        win32api.keybd_event(0x31 + node.tab_idx, 0, 2, 0)
                        win32api.keybd_event(0x11, 0, 2, 0)
        except: pass
    threading.Thread(target=_go, daemon=True).start()

def activate_node(node: WNode, on_opened=None):
    """Activate a node: focus real window, or open preset URL in browser."""
    if node.preset_url:
        def _open():
            webbrowser.open(node.preset_url)
            if on_opened:
                time.sleep(2.5)
                try: on_opened()
                except: pass
        threading.Thread(target=_open, daemon=True).start()
    else:
        focus_node(node)

# ── Branch overlay window ─────────────────────────────────────────────────────
class BranchOverlay:
    def __init__(self, root: tk.Tk, osc: Oscillator, state: dict, on_close,
                 active_preset: list = None):
        self._root     = root
        self._osc      = osc
        self._state    = state
        self._on_close = on_close
        self._settings_open = False
        self._zones_open    = False
        self._nodes: List[WNode] = []
        self._bc: Optional[BranchCanvas] = None
        self._active_preset: list = active_preset or []   # list of {title,url,color,zone_label}

        self.win = tk.Toplevel(root)
        self.win.configure(bg=BG)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.10)
        self.win.attributes("-fullscreen", True)
        self.win.title(f"Branch v{__version__}")
        self.win.focus_force()

        self.win.bind("<Escape>", lambda e: self._close())
        self.win.bind("<F5>",     lambda e: self._rescan())
        self.win.bind("<space>",  lambda e: self._advance())
        self.win.bind("<Return>", lambda e: self._go_active())

        self._note_open = False
        self._build_chrome()
        self._rescan()
        self._osc.start(lambda: root.after(0, self._advance))
        self._start_wiggle_watch()

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
            ("✕ Close (Esc)", self._close,         RED),
            ("⊞ Zones",       self._open_zones,    PURPLE),
            ("⚙ Settings",    self._open_settings, BLUE),
            ("↻ Scan (F5)",   self._rescan,        GREEN),
        ]:
            tk.Button(bar, text=txt, font=("Segoe UI", 8),
                      fg=col, bg=BG2, activebackground=BG3,
                      activeforeground=col, relief="flat",
                      padx=10, pady=2, cursor="hand2",
                      command=cmd).pack(side="right", padx=1)

        # Play/pause button
        self._paused = False
        self._pp_btn = tk.Button(bar, text="⏸ Pause", font=("Segoe UI", 8, "bold"),
                                  fg=YELLOW, bg=BG2, activebackground=BG3,
                                  activeforeground=YELLOW, relief="flat",
                                  padx=10, pady=2, cursor="hand2",
                                  command=self._toggle_pause)
        self._pp_btn.pack(side="right", padx=1)

        # Preset indicator bar (shown only when a preset is active)
        self._preset_bar  = tk.Frame(self.win, bg="#1a1a2e", pady=2)
        self._preset_name = tk.Label(self._preset_bar, text="",
                                      font=("Segoe UI", 8, "bold"),
                                      fg=PURPLE, bg="#1a1a2e")
        self._preset_name.pack(side="left", padx=12)
        self._preset_count= tk.Label(self._preset_bar, text="",
                                      font=("Segoe UI", 7), fg=FG_DIM, bg="#1a1a2e")
        self._preset_count.pack(side="left", padx=4)
        tk.Button(self._preset_bar, text="✕ clear preset", font=("Segoe UI", 7),
                  fg=FG_DIM, bg="#1a1a2e", relief="flat", padx=6, cursor="hand2",
                  command=self._clear_preset).pack(side="right", padx=8)
        if self._active_preset:
            self._preset_bar.pack(fill="x", after=bar)

        # Canvas area (filled between bar and hint)
        self._canvas_host = tk.Frame(self.win, bg=BG)
        self._canvas_host.pack(fill="both", expand=True)

        # Bottom hint
        hint = tk.Frame(self.win, bg=BG2, pady=3)
        hint.pack(fill="x", side="bottom")
        tk.Label(hint,
                 text="Oscillator cycles windows live  ·  Click/Enter = jump or open  ·  "
                      "Preset nodes ⊕ open in browser on click  ·  Wiggle ← → ← → = note  ·  Esc = close",
                 font=("Segoe UI", 7), fg=FG_DIM, bg=BG2).pack()

    def _clear_preset(self):
        """Remove preset nodes and hide the indicator bar."""
        self._active_preset = []
        try: self._preset_bar.pack_forget()
        except: pass
        self._rescan()

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._osc.stop()
            self._pp_btn.config(text="▶ Play")
        else:
            self._osc.start(lambda: self._root.after(0, self._advance))
            self._pp_btn.config(text="⏸ Pause")

    def _start_wiggle_watch(self):
        """Background thread: detect rapid mouse direction reversals → note popup."""
        history = []   # (x, timestamp)
        WINDOW_MS  = 600    # look-back window
        REVERSALS  = 4      # direction changes needed
        MIN_DIST   = 30     # pixels per movement to count

        def _watch():
            prev_x = None
            prev_dir = 0
            rev_count = 0
            rev_times = []

            while getattr(self, '_watching', True):
                time.sleep(0.04)
                try:
                    pt = win32api.GetCursorPos()
                    x = pt[0]
                    if prev_x is None:
                        prev_x = x; continue
                    dx = x - prev_x
                    if abs(dx) < MIN_DIST / 4:
                        prev_x = x; continue
                    direction = 1 if dx > 0 else -1
                    if prev_dir != 0 and direction != prev_dir and abs(dx) > MIN_DIST / 4:
                        rev_count += 1
                        rev_times.append(time.time())
                    prev_dir = direction
                    prev_x = x

                    # Clear old events outside window
                    now = time.time()
                    rev_times = [t for t in rev_times if now - t < WINDOW_MS / 1000]
                    rev_count = len(rev_times)

                    if rev_count >= REVERSALS:
                        rev_times.clear()
                        rev_count = 0
                        # Fire note popup on main thread
                        if self._bc:
                            node = self._bc.get_active_node()
                            if node:
                                self._root.after(0, lambda n=node: self._note_popup(n))
                except: pass

        self._watching = True
        threading.Thread(target=_watch, daemon=True).start()

    def _rescan(self):
        self._status_lbl.config(text="Scanning…", fg=YELLOW)

        def _work():
            nodes = scan_windows()
            sw    = self.win.winfo_screenwidth()
            sh    = self.win.winfo_screenheight()

            # Merge preset bookmarks: only add those not already open
            preset = self._active_preset
            if preset:
                from urllib.parse import urlparse
                open_domains = set()
                for n in flatten(nodes):
                    # Collect domains from tab titles (browser tabs include domain in title)
                    t = n.title.lower()
                    for seg in t.replace("—"," ").replace("-"," ").replace("|"," ").split():
                        if "." in seg: open_domains.add(seg.strip("."))
                for item in preset:
                    url = item.get("url","")
                    if not url: continue
                    try:
                        domain = urlparse(url).netloc.lower().replace("www.","")
                        domain_key = domain.split(".")[0]  # e.g. "nationwide"
                    except: continue
                    # Skip if that domain appears to already be open
                    already = any(domain_key in d for d in open_domains)
                    if not already:
                        pn = WNode(
                            hwnd=0, title=item["title"], exe="bookmark",
                            color=item.get("color", PURPLE),
                            preset_url=url,
                            zone_label=item.get("zone_label",""))
                        nodes.append(pn)

            layout_radial(nodes, sw / 2, sh / 2)
            self._root.after(0, lambda: self._apply(nodes))

        threading.Thread(target=_work, daemon=True).start()

    def _apply(self, nodes: List[WNode]):
        self._nodes = nodes
        flat     = flatten(nodes)
        real_win = [n for n in flat if not n.preset_url and not n.is_tab]
        real_tab = [n for n in flat if not n.preset_url and n.is_tab]
        presets  = [n for n in flat if n.preset_url]
        parts    = [f"{len(real_win)} windows", f"{len(real_tab)} tabs"]
        if presets:
            parts.append(f"{len(presets)} preset")
        self._status_lbl.config(text="  ·  ".join(parts), fg=FG_DIM)

        # Update preset indicator
        if self._active_preset:
            try:
                name = getattr(self, '_preset_name_str', "Preset")
                self._preset_name.config(text=f"🗺 {name}")
                opened = len(self._active_preset) - len(presets)
                self._preset_count.config(
                    text=f"{opened}/{len(self._active_preset)} open  ·  "
                         f"{len(presets)} waiting — click to open",
                    fg=GREEN if opened == len(self._active_preset) else FG_DIM)
            except: pass

        if self._bc:
            self._bc.destroy()
        self._bc = BranchCanvas(self._canvas_host, nodes,
                                on_select=self._select)
        self._bc.pack(fill="both", expand=True)

    def _advance(self):
        if not self._bc: return
        self._bc.set_active(self._bc._active + 1)
        node = self._bc.get_active_node()
        if node and not node.preset_url:
            focus_node(node)   # oscillator only cycles real windows — preset nodes just highlight

    def _go_active(self):
        if self._bc:
            node = self._bc.get_active_node()
            if node:
                if node.preset_url:
                    activate_node(node, on_opened=lambda: self._root.after(0, self._rescan))
                else:
                    self._close()
                    activate_node(node)

    def _select(self, node: WNode):
        if node.preset_url:
            activate_node(node, on_opened=lambda: self._root.after(0, self._rescan))
        else:
            self._close()
            activate_node(node)

    def _note_popup(self, node: WNode):
        """Small note popup for the currently highlighted window/tab."""
        if getattr(self, '_note_open', False): return
        self._note_open = True

        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        pop = tk.Toplevel(self.win)
        pop.configure(bg=BG2)
        pop.attributes("-topmost", True)
        pop.attributes("-alpha", 0.95)
        pop.resizable(False, False)
        pop.geometry(f"320x130+{sw//2-160}+{sh//2-65}")
        pop.overrideredirect(True)   # borderless

        title = (node.title[:40] + "…") if len(node.title) > 40 else node.title
        tk.Label(pop, text=title, font=("Segoe UI", 8, "bold"),
                 fg=BLUE, bg=BG2, anchor="w").pack(fill="x", padx=10, pady=(10,2))
        tk.Label(pop, text="What are you doing here?",
                 font=("Segoe UI", 9), fg=FG, bg=BG2).pack(anchor="w", padx=10)

        entry = tk.Entry(pop, font=("Segoe UI", 10), bg=BG3, fg=FG,
                         insertbackground=BLUE, relief="flat",
                         highlightthickness=1, highlightbackground=BLUE)
        entry.pack(fill="x", padx=10, pady=(4, 0), ipady=5)
        entry.focus_force()

        def _save(e=None):
            text = entry.get().strip()
            if text:
                notes = []
                nf = SCRIPT_DIR / "windowbranch_notes.json"
                if nf.exists():
                    try: notes = json.load(open(nf))
                    except: pass
                notes.append({
                    "ts":    time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "window": node.title,
                    "exe":   node.exe,
                    "note":  text,
                    "is_tab": node.is_tab,
                })
                try: json.dump(notes[-200:], open(nf, "w"), indent=2)
                except: pass
            pop.destroy()
            self._note_open = False

        def _cancel(e=None):
            pop.destroy()
            self._note_open = False

        btn_row = tk.Frame(pop, bg=BG2)
        btn_row.pack(fill="x", padx=10, pady=6)
        tk.Button(btn_row, text="Save  ↵", font=("Segoe UI", 8, "bold"),
                  fg=BG, bg=GREEN, relief="flat", padx=10, pady=2,
                  command=_save).pack(side="right", padx=(4,0))
        tk.Button(btn_row, text="Skip", font=("Segoe UI", 8),
                  fg=FG_DIM, bg=BG3, relief="flat", padx=8, pady=2,
                  command=_cancel).pack(side="right")

        entry.bind("<Return>", _save)
        entry.bind("<Escape>", _cancel)

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
        self._watching = False
        self._osc.stop()
        try: self.win.destroy()
        except: pass
        self._on_close()

# ── Playground ────────────────────────────────────────────────────────────────
import urllib.request as _ureq
import io           as _io
import uuid         as _uuid_mod
import webbrowser   as _wb
import copy         as _copy

PLAYGROUND_FILE = SCRIPT_DIR / "windowbranch_playground.json"
FAVICON_DIR     = SCRIPT_DIR / ".playground_favicons"
SHAPES          = ["rounded", "circle", "square", "hexagon", "cabin", "pill", "diamond"]

ZONE_COLORS = {
    "money":    "#ffd43b", "wishlist": "#d2a8ff", "news":    "#79c0ff",
    "todo":     "#ffa657", "socials":  "#ff7b72", "food":    "#e3b341",
    "subs":     "#76e3ea", "daily":    "#7ee787", "hustle":  "#94e2d5",
    "personal": "#89b4fa",
}

def _blend(hex_col: str, alpha: float, base: str = BG) -> str:
    def p(h):
        h = h.lstrip("#")
        return int(h[:2],16), int(h[2:4],16), int(h[4:6],16)
    r1,g1,b1 = p(hex_col); r2,g2,b2 = p(base)
    return "#{:02x}{:02x}{:02x}".format(
        int(r1*alpha+r2*(1-alpha)), int(g1*alpha+g2*(1-alpha)), int(b1*alpha+b2*(1-alpha)))

def _mk_node(title, url, zone, shape="rounded"):
    return {"id": str(_uuid_mod.uuid4())[:8], "title": title, "url": url,
            "zone_id": zone, "shape": shape, "color": ZONE_COLORS.get(zone, BLUE),
            "xf": 0.0, "yf": 0.0, "w": 110, "h": 32}

def _mk_zone(zid, title, cx, cy, w, h, nodes=None):
    return {"id": zid, "title": title, "color": ZONE_COLORS.get(zid, BLUE),
            "cx": cx, "cy": cy, "w": w, "h": h, "nodes": nodes or []}

LAURENCE_PRESET = {
    "name": "Laurence's Every Day",
    "zones": [
        _mk_zone("money",    "💰 Money",          0.15, 0.23, 0.22, 0.30, [
            _mk_node("Nationwide",       "https://www.nationwide.co.uk",                           "money"),
            _mk_node("NatWest",          "https://www.natwest.com",                                "money"),
            _mk_node("Salary Calc",      "https://www.thesalarycalculator.co.uk/",                 "money"),
            _mk_node("PayPal",           "https://www.paypal.com/uk/home",                         "money"),
        ]),
        _mk_zone("daily",    "✅ Daily Check-in",  0.82, 0.25, 0.24, 0.36, [
            _mk_node("Gmail",            "https://mail.google.com",                                "daily"),
            _mk_node("Google Calendar",  "https://calendar.google.com",                            "daily"),
            _mk_node("Universal Credit", "https://www.gov.uk/sign-in-universal-credit",            "daily"),
            _mk_node("Heathcot Surgery", "https://systmonline.tpp-uk.com/",                        "daily"),
            _mk_node("Fuel MPG",         "https://www.mpg-calculator.co.uk/",                      "daily"),
            _mk_node("Child Maint.",     "https://www.gov.uk/child-maintenance-service/sign-in-account","daily"),
        ]),
        _mk_zone("news",     "📰 News",             0.46, 0.13, 0.20, 0.20, [
            _mk_node("BBC News",         "https://www.bbc.co.uk/news",                             "news"),
            _mk_node("YouTube",          "https://www.youtube.com",                                "news"),
            _mk_node("Google",           "https://www.google.com",                                 "news"),
            _mk_node("Sheets",           "https://sheets.google.com",                              "news"),
        ]),
        _mk_zone("hustle",   "💸 Side Hustle",      0.69, 0.14, 0.18, 0.20, [
            _mk_node("FB Marketplace",   "https://www.facebook.com/marketplace",                   "hustle"),
            _mk_node("Vinted",           "https://www.vinted.co.uk",                               "hustle"),
            _mk_node("eBay",             "https://www.ebay.co.uk",                                 "hustle"),
            _mk_node("Whatnot",          "https://www.whatnot.com",                                "hustle"),
        ]),
        _mk_zone("socials",  "📱 Socials",          0.48, 0.53, 0.16, 0.24, [
            _mk_node("Facebook",         "https://www.facebook.com",                               "socials"),
            _mk_node("YouTube",          "https://www.youtube.com",                                "socials"),
            _mk_node("TikTok",           "https://www.tiktok.com",                                 "socials"),
        ]),
        _mk_zone("food",     "🍔 Food",              0.32, 0.74, 0.30, 0.22, [
            _mk_node("Uber Eats",        "https://www.ubereats.com/gb",                            "food"),
            _mk_node("Tesco",            "https://www.tesco.com",                                  "food"),
            _mk_node("ASDA",             "https://www.asda.com",                                   "food"),
            _mk_node("Sainsbury's",      "https://www.sainsburys.co.uk",                           "food"),
            _mk_node("Morrisons",        "https://groceries.morrisons.com",                        "food"),
            _mk_node("Waitrose",         "https://www.waitrose.com",                               "food"),
            _mk_node("Ocado",            "https://www.ocado.com",                                  "food"),
        ]),
        _mk_zone("subs",     "🔄 Subscriptions",    0.80, 0.60, 0.22, 0.18, [
            _mk_node("Releaf Cannabis",  "https://releaf.co.uk/",                                  "subs"),
            _mk_node("Play Store Subs",  "https://play.google.com/store/account/subscriptions",    "subs"),
        ]),
        _mk_zone("wishlist", "🛒 Wishlist",          0.12, 0.70, 0.20, 0.26, [
            _mk_node("Argos",            "https://www.argos.co.uk",                                "wishlist"),
            _mk_node("eBay",             "https://www.ebay.co.uk",                                 "wishlist"),
            _mk_node("Amazon UK",        "https://www.amazon.co.uk",                              "wishlist"),
            _mk_node("ASOS",             "https://www.asos.com",                                   "wishlist"),
        ]),
        _mk_zone("todo",     "📋 Things To Do",      0.82, 0.82, 0.20, 0.14, [
            _mk_node("Woking Council",   "https://www.woking.gov.uk/your-council/have-your-say/complaints/make-complaint","todo"),
        ]),
        _mk_zone("personal", "🏠 Personal",          0.62, 0.51, 0.22, 0.24, [
            _mk_node("Stock Map",        "https://finviz.com/map.ashx",                            "personal"),
            _mk_node("Weather Woking",   "https://www.google.com/search?q=weather+woking+GU21",    "personal"),
            _mk_node("Telegram",         "https://web.telegram.org",                               "personal"),
        ]),
    ]
}

# ── Shape drawing ─────────────────────────────────────────────────────────────
def _draw_shape(c: tk.Canvas, shape: str, x, y, w, h,
                fill="", outline=BLUE, width=1, tags=()):
    hw, hh = w/2, h/2
    x1, y1, x2, y2 = x-hw, y-hh, x+hw, y+hh
    ids = []
    if shape == "circle":
        r = min(hw, hh)
        ids += [c.create_oval(x-r, y-r, x+r, y+r,
                              fill=fill, outline=outline, width=width, tags=tags)]
    elif shape == "square":
        ids += [c.create_rectangle(x1, y1, x2, y2,
                                   fill=fill, outline=outline, width=width, tags=tags)]
    elif shape == "hexagon":
        pts = []
        for i in range(6):
            a = math.pi/2 + i*math.pi/3
            pts += [x + min(hw, hh)*math.cos(a), y - min(hw, hh)*math.sin(a)]
        ids += [c.create_polygon(*pts, fill=fill, outline=outline, width=width, tags=tags)]
    elif shape == "cabin":
        ids += [c.create_polygon(
            x, y1, x+hw, y1+hh*0.5, x+hw, y2, x-hw, y2, x-hw, y1+hh*0.5,
            fill=fill, outline=outline, width=width, tags=tags)]
    elif shape == "pill":
        ids += [c.create_oval(x1, y1, x2, y2,
                              fill=fill, outline=outline, width=width, tags=tags)]
    elif shape == "diamond":
        ids += [c.create_polygon(x, y1, x2, y, x, y2, x1, y,
                                 fill=fill, outline=outline, width=width, tags=tags)]
    else:  # "rounded"
        r = min(10, hh*0.45)
        pts = [x1+r,y1, x2-r,y1, x2,y1+r, x2,y2-r, x2-r,y2, x1+r,y2, x1,y2-r, x1,y1+r]
        ids += [c.create_polygon(*pts, smooth=True,
                                 fill=fill, outline=outline, width=width, tags=tags)]
    return ids

# ── Favicon loader ────────────────────────────────────────────────────────────
class FaviconLoader:
    _mem:     dict = {}
    _pending: set  = set()
    _lock          = threading.Lock()

    @classmethod
    def get(cls, url: str, on_done) -> None:
        from urllib.parse import urlparse
        try:    domain = urlparse(url).netloc.lower()
        except: on_done(None); return
        if not domain: on_done(None); return
        with cls._lock:
            if domain in cls._mem:   on_done(cls._mem[domain]); return
            if domain in cls._pending: return
            cls._pending.add(domain)
        def _fetch():
            img = None
            try:
                FAVICON_DIR.mkdir(exist_ok=True)
                cp = FAVICON_DIR / f"{domain.replace('/','_').replace(':','_')}.png"
                if cp.exists():
                    img = PILImage.open(cp).convert("RGBA").resize((16,16), PILImage.LANCZOS)
                else:
                    req = _ureq.Request(
                        f"https://www.google.com/s2/favicons?domain={domain}&sz=32",
                        headers={"User-Agent":"Mozilla/5.0"})
                    raw = _ureq.urlopen(req, timeout=5).read()
                    img = PILImage.open(_io.BytesIO(raw)).convert("RGBA").resize((16,16), PILImage.LANCZOS)
                    img.save(cp, "PNG")
            except: pass
            with cls._lock:
                cls._mem[domain] = img
                cls._pending.discard(domain)
            on_done(img)
        threading.Thread(target=_fetch, daemon=True).start()

# ── Playground overlay ────────────────────────────────────────────────────────
class PlaygroundOverlay:
    """Full-screen zones board. Click = open URL. Edit mode = drag & reshape nodes."""

    def __init__(self, app: "BranchApp"):
        self._app       = app
        self._edit      = False
        self._data      = self._load_data()
        self._laid_out  = False
        self._fav_imgs: dict = {}    # nid → tk.PhotoImage (keep-alive)
        self._hover_id  = None       # node id string
        self._drag_nid  = None
        self._drag_nd   = None
        self._pan       = [0.0, 0.0]
        self._scale     = 1.0
        self._pan_start = None
        self._node_map: dict = {}    # canvas_item_id → node dict
        self._zone_map: dict = {}

        self.win = tk.Toplevel(app.root)
        self.win.configure(bg=BG)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.97)
        self.win.attributes("-fullscreen", True)
        self.win.title("Playground")
        self._build_ui()
        self.win.bind("<Escape>", lambda e: self._close())
        self.win.after(120, self._draw)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_data(self) -> dict:
        if PLAYGROUND_FILE.exists():
            try:
                with open(PLAYGROUND_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return _copy.deepcopy(LAURENCE_PRESET)

    def _save(self):
        try:
            with open(PLAYGROUND_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            self._status.config(text="Saved  ✓", fg=GREEN)
            self.win.after(2000, lambda: self._status.config(
                text="Drag to move  ·  dbl-click = change shape" if self._edit
                else "Click = open in browser  ·  Ctrl+E = edit",
                fg=FG_DIM if not self._edit else YELLOW))
        except Exception as ex:
            self._status.config(text=f"Save failed: {ex}", fg=RED)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        bar = tk.Frame(self.win, bg=BG2, pady=4)
        bar.pack(fill="x", side="top")

        tk.Label(bar, text="🎮 Playground",
                 font=("Consolas", 11, "bold"), fg=PURPLE, bg=BG2).pack(side="left", padx=12)

        self._edit_btn = tk.Button(
            bar, text="✏  Edit Mode", font=("Segoe UI", 8),
            fg=YELLOW, bg=BG2, activebackground=BG3,
            relief="flat", padx=10, pady=2, cursor="hand2",
            command=self._toggle_edit)
        self._edit_btn.pack(side="left", padx=4)

        for txt, col, cmd in [
            ("Laurence Preset", GREEN, self._load_laurence),
            ("Import JSON",     BLUE,  self._import_json),
            ("Export JSON",     TEAL,  self._export_json),
            ("💾 Save",         GREEN, self._save),
        ]:
            tk.Button(bar, text=txt, font=("Segoe UI", 8), fg=col, bg=BG2,
                      activebackground=BG3, relief="flat", padx=8, pady=2,
                      cursor="hand2", command=cmd).pack(side="left", padx=2)

        self._status = tk.Label(
            bar, text="Click a node to open  ·  Ctrl+E = edit mode",
            font=("Segoe UI", 7), fg=FG_DIM, bg=BG2)
        self._status.pack(side="left", padx=10)

        tk.Button(bar, text="✕ Close (Esc)", font=("Segoe UI", 8),
                  fg=RED, bg=BG2, activebackground=BG3, relief="flat",
                  padx=10, pady=2, cursor="hand2",
                  command=self._close).pack(side="right", padx=4)

        # Shape palette row (hidden until edit mode)
        self._shape_row = tk.Frame(self.win, bg=BG3, pady=3)
        self._shape_var = tk.StringVar(value="rounded")
        tk.Label(self._shape_row, text="Shape:",
                 font=("Segoe UI", 8, "bold"), fg=FG, bg=BG3).pack(side="left", padx=(12,4))
        for sh in SHAPES:
            tk.Radiobutton(
                self._shape_row, text=sh.title(), variable=self._shape_var, value=sh,
                font=("Segoe UI", 8), fg=FG, bg=BG3, selectcolor=BG2,
                activebackground=BG3, cursor="hand2"
            ).pack(side="left", padx=5)
        tk.Label(self._shape_row,
                 text="   ← select then double-click a node to apply",
                 font=("Segoe UI", 7), fg=FG_DIM, bg=BG3).pack(side="left", padx=6)

        hint = tk.Frame(self.win, bg=BG2, pady=3)
        hint.pack(fill="x", side="bottom")
        tk.Label(hint,
                 text="Click = open browser  ·  Ctrl+E = edit  ·  Scroll = zoom  "
                      "·  Right-drag = pan  ·  Esc = close",
                 font=("Segoe UI", 7), fg=FG_DIM, bg=BG2).pack()

        self._c = tk.Canvas(self.win, bg=BG, highlightthickness=0, cursor="arrow")
        self._c.pack(fill="both", expand=True)

        self._c.bind("<Configure>",        self._on_resize)
        self._c.bind("<Motion>",           self._on_hover)
        self._c.bind("<Button-1>",         self._on_lclick)
        self._c.bind("<Double-Button-1>",  self._on_dbl)
        self._c.bind("<B1-Motion>",        self._on_drag)
        self._c.bind("<ButtonRelease-1>",  self._on_release)
        self._c.bind("<ButtonPress-3>",    self._pan_begin)
        self._c.bind("<B3-Motion>",        self._pan_do)
        self._c.bind("<ButtonPress-2>",    self._pan_begin)
        self._c.bind("<B2-Motion>",        self._pan_do)
        self._c.bind("<MouseWheel>",       self._zoom)
        self.win.bind("<Control-e>",       lambda e: self._toggle_edit())

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _cw(self): return self._c.winfo_width()  or 1200
    def _ch(self): return self._c.winfo_height() or 800

    def _fw(self, xf): return xf * self._cw() * self._scale + self._pan[0]
    def _fh(self, yf): return yf * self._ch() * self._scale + self._pan[1]

    def _zone_rect(self, zone: dict):
        cx = self._fw(zone["cx"])
        cy = self._fh(zone["cy"])
        zw = zone["w"] * self._cw() * self._scale
        zh = zone["h"] * self._ch() * self._scale
        return cx - zw/2, cy - zh/2, zw, zh

    def _to_frac(self, sx, sy):
        sc = self._scale or 1.0
        return ((sx - self._pan[0]) / (self._cw() * sc),
                (sy - self._pan[1]) / (self._ch() * sc))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _layout_nodes(self):
        for zone in self._data.get("zones", []):
            zx, zy, zw, zh = self._zone_rect(zone)
            nodes = [n for n in zone.get("nodes", [])
                     if n.get("xf", 0.0) == 0.0 and n.get("yf", 0.0) == 0.0]
            if not nodes: continue
            pad = 8; hdr = 24
            avail_w = max(60, zw - 2*pad)
            n = len(nodes)
            cols = max(1, math.ceil(math.sqrt(n * avail_w / max(1, zh - hdr))))
            nw = max(50, (avail_w - (cols-1)*5) / cols)
            nh = 30
            for i, nd in enumerate(nodes):
                col = i % cols; row = i // cols
                sx = zx + pad + col*(nw+5) + nw/2
                sy = zy + hdr + pad + row*(nh+6) + nh/2
                nd["xf"], nd["yf"] = self._to_frac(sx, sy)
                nd["w"], nd["h"] = nw, nh
        self._laid_out = True

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw(self):
        c = self._c
        if not self._laid_out:
            self._layout_nodes()
            self.win.after(200, self._load_favicons)
        c.delete("all")
        self._node_map.clear()
        self._zone_map.clear()

        for zone in self._data.get("zones", []):
            zx, zy, zw, zh = self._zone_rect(zone)
            col = zone.get("color", BLUE)
            fill_col = _blend(col, 0.13)
            r = min(14, zh*0.05, zw*0.05)
            pts = [zx+r,zy, zx+zw-r,zy, zx+zw,zy+r, zx+zw,zy+zh-r,
                   zx+zw-r,zy+zh, zx+r,zy+zh, zx,zy+zh-r, zx,zy+r]
            zid = c.create_polygon(*pts, smooth=True,
                                   fill=fill_col, outline=col, width=1, tags="zone")
            self._zone_map[zid] = zone
            hdr_h = min(22, zh*0.15)
            c.create_text(zx+10, zy+hdr_h/2, text=zone.get("title",""),
                          font=("Segoe UI", 8, "bold"), fill=col, anchor="w")

            for nd in zone.get("nodes", []):
                nx = self._fw(nd.get("xf", zone["cx"]))
                ny = self._fh(nd.get("yf", zone["cy"]))
                nw = max(44, nd.get("w", 100) * self._scale)
                nh = max(18, nd.get("h", 30) * self._scale)
                ncol = nd.get("color", col)
                is_hov = nd.get("id") == self._hover_id
                fill_n = _blend(ncol, 0.4 if is_hov else 0.2)
                out_n  = ncol if is_hov else _blend(ncol, 0.6)
                lw     = 2 if is_hov else 1
                sids = _draw_shape(c, nd.get("shape","rounded"), nx, ny, nw, nh,
                                   fill=fill_n, outline=out_n, width=lw, tags="node")
                for sid in sids:
                    self._node_map[sid] = nd

                # Favicon
                fav = self._fav_imgs.get(nd.get("id",""))
                tx_off = 0
                if fav:
                    fid = c.create_image(nx - nw/2 + 11, ny, image=fav,
                                         anchor="center", tags="node")
                    self._node_map[fid] = nd
                    tx_off = 9

                # Label
                chars = max(3, int(nw / 6.8))
                title = nd.get("title","")
                if len(title) > chars: title = title[:chars-1]+"…"
                tid = c.create_text(
                    nx + tx_off, ny, text=title,
                    font=("Segoe UI", 7, "bold" if is_hov else "normal"),
                    fill=FG if is_hov else _blend(FG, 0.75),
                    anchor="center", width=nw-6, tags="node")
                self._node_map[tid] = nd

                if self._edit:
                    c.create_oval(nx+nw/2-8, ny-nh/2+1,
                                  nx+nw/2-2, ny-nh/2+7,
                                  fill=YELLOW, outline="", tags="node")

    # ── Favicons (background thread pool, disk + memory cache) ────────────────

    def _load_favicons(self):
        from PIL import ImageTk as _ItK
        for zone in self._data.get("zones", []):
            for nd in zone.get("nodes", []):
                nid = nd.get("id",""); url = nd.get("url","")
                if not url or nid in self._fav_imgs: continue
                def _done(pil_img, _nid=nid):
                    if pil_img is None: return
                    try:
                        self._fav_imgs[_nid] = _ItK.PhotoImage(pil_img)
                        try: self.win.after(0, self._draw)
                        except: pass
                    except: pass
                FaviconLoader.get(url, _done)

    # ── Interaction ───────────────────────────────────────────────────────────

    def _hit_node(self, ex, ey):
        for iid in self._c.find_closest(ex, ey, halo=12):
            if iid in self._node_map:
                return self._node_map[iid]
        return None

    def _on_hover(self, e):
        nd = self._hit_node(e.x, e.y)
        new_id = nd.get("id","") if nd else None
        if new_id != self._hover_id:
            self._hover_id = new_id
            self._draw()
            self._c.config(cursor=("hand2" if nd else ("fleur" if self._edit else "arrow")))

    def _on_lclick(self, e):
        if self._edit:
            nd = self._hit_node(e.x, e.y)
            self._drag_nid = nd.get("id") if nd else None
            self._drag_nd  = nd
            return
        nd = self._hit_node(e.x, e.y)
        if nd:
            url = nd.get("url","")
            if url:
                threading.Thread(target=lambda: _wb.open(url), daemon=True).start()

    def _on_dbl(self, e):
        nd = self._hit_node(e.x, e.y)
        if not nd: return
        if self._edit:
            nd["shape"] = self._shape_var.get()
            self._draw()
        else:
            url = nd.get("url","")
            if url:
                threading.Thread(target=lambda: _wb.open(url), daemon=True).start()

    def _on_drag(self, e):
        if not self._edit or not self._drag_nid: return
        nd = self._drag_nd
        if nd:
            nd["xf"], nd["yf"] = self._to_frac(e.x, e.y)
            self._draw()

    def _on_release(self, e):
        self._drag_nid = None
        self._drag_nd  = None

    def _pan_begin(self, e):
        self._pan_start = (e.x, e.y, self._pan[0], self._pan[1])

    def _pan_do(self, e):
        if not self._pan_start: return
        sx, sy, px, py = self._pan_start
        self._pan[0] = px + e.x - sx
        self._pan[1] = py + e.y - sy
        self._draw()

    def _zoom(self, e):
        f = 1.1 if e.delta > 0 else 0.9
        old = self._scale
        self._scale = max(0.25, min(3.5, self._scale * f))
        # Zoom toward mouse pointer
        ratio = self._scale / old
        self._pan[0] = e.x + (self._pan[0] - e.x) * ratio
        self._pan[1] = e.y + (self._pan[1] - e.y) * ratio
        self._draw()

    def _on_resize(self, e):
        if self._laid_out:
            self._draw()
        else:
            self._layout_nodes()
            self._draw()
            self.win.after(300, self._load_favicons)

    # ── Edit toggle ───────────────────────────────────────────────────────────

    def _toggle_edit(self):
        self._edit = not self._edit
        if self._edit:
            self._edit_btn.config(text="👁  View Mode", fg=GREEN)
            self._shape_row.pack(fill="x", side="top", before=self._c)
            self._status.config(
                text="Drag to move  ·  double-click node = apply shape  ·  Ctrl+E = exit edit",
                fg=YELLOW)
            self._c.config(cursor="fleur")
        else:
            self._edit_btn.config(text="✏  Edit Mode", fg=YELLOW)
            self._shape_row.pack_forget()
            self._status.config(text="Click = open in browser  ·  Ctrl+E = edit mode", fg=FG_DIM)
            self._c.config(cursor="arrow")
        self._draw()

    # ── Preset / Import / Export ──────────────────────────────────────────────

    def _load_laurence(self):
        self._data     = _copy.deepcopy(LAURENCE_PRESET)
        self._laid_out = False
        self._fav_imgs.clear()
        FaviconLoader._mem.clear()
        self.win.after(100, lambda: (self._layout_nodes(), self._draw(),
                                     self.win.after(300, self._load_favicons)))

    def _import_json(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Import Playground JSON",
            filetypes=[("JSON","*.json"),("All","*.*")],
            parent=self.win)
        if not path: return
        try:
            with open(path,"r",encoding="utf-8") as f:
                self._data = json.load(f)
            self._laid_out = False
            self._fav_imgs.clear()
            self.win.after(100, lambda: (self._layout_nodes(), self._draw(),
                                         self.win.after(300, self._load_favicons)))
        except Exception as ex:
            self._status.config(text=f"Import error: {ex}", fg=RED)

    def _export_json(self):
        from tkinter import filedialog
        name = self._data.get("name","preset").replace(" ","_")
        path = filedialog.asksaveasfilename(
            title="Export Playground JSON",
            defaultextension=".json",
            filetypes=[("JSON","*.json")],
            parent=self.win,
            initialfile=f"playground_{name}.json")
        if not path: return
        try:
            with open(path,"w",encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            self._status.config(text=f"Exported  ✓", fg=TEAL)
        except Exception as ex:
            self._status.config(text=f"Export error: {ex}", fg=RED)

    # ── Close ─────────────────────────────────────────────────────────────────

    def _close(self):
        try: self.win.destroy()
        except: pass
        try: self._app._playground = None
        except: pass

# ── App ────────────────────────────────────────────────────────────────────────
class BranchApp:
    def __init__(self):
        self.root      = tk.Tk()
        self.root.withdraw()
        self._state    = _load_state()
        self._osc      = Oscillator(self._state)
        self._overlay:    Optional[BranchOverlay] = None
        self._tray_icon   = None
        self._active_preset:     list = []   # [{title,url,color,zone_label}]
        self._active_preset_name: str = ""

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
            on_close=self._overlay_closed,
            active_preset=list(self._active_preset))
        if self._active_preset_name:
            self._overlay._preset_name_str = self._active_preset_name

    def _activate_preset_zones(self, zones: list, name: str = "Preset"):
        """Flatten preset zones into bookmark list and push to overlay."""
        items = []
        for zone in zones:
            col = zone.get("color", ZONE_COLORS.get(zone.get("id",""), PURPLE))
            zone_title = zone.get("title","")
            for nd in zone.get("nodes", []):
                items.append({
                    "title":      nd.get("title",""),
                    "url":        nd.get("url",""),
                    "color":      nd.get("color", col),
                    "zone_label": zone_title,
                })
        self._active_preset      = items
        self._active_preset_name = name
        if self._overlay:
            self._overlay._active_preset      = list(items)
            self._overlay._preset_name_str    = name
            try: self._overlay._preset_bar.pack(fill="x")
            except: pass
            self._overlay._rescan()

    def _load_and_activate_laurence(self):
        """Load Laurence preset — from edited playground file if it exists, else default."""
        data = _copy.deepcopy(LAURENCE_PRESET)
        if PLAYGROUND_FILE.exists():
            try:
                with open(PLAYGROUND_FILE,"r",encoding="utf-8") as f:
                    saved = json.load(f)
                if saved.get("zones"): data = saved
            except: pass
        def _do():
            self._activate_preset_zones(data.get("zones",[]), data.get("name","Laurence's Every Day"))
            if not self._overlay:
                self._show()
        self.root.after(0, _do)

    def _overlay_closed(self):
        self._overlay = None
        self._osc = Oscillator(self._state)   # fresh oscillator for next show
        self._state.update(self._osc.to_state())

    def _clear_tray_preset(self):
        self._active_preset      = []
        self._active_preset_name = ""
        if self._overlay:
            self._overlay._clear_preset()

    def _idle_check(self):
        idle_mins = self._state.get("auto_idle_minutes", 0)
        if idle_mins > 0 and not self._overlay:
            if idle_ms() >= idle_mins * 60_000:
                self._show()
        self.root.after(10_000, self._idle_check)

    def _set_alpha(self, a: float):
        self._state["alpha"] = a
        if self._overlay:
            self._overlay.win.attributes("-alpha", a)

    def _set_speed(self, base_ms: int, label: str):
        self._osc.base_ms = base_ms
        self._state["osc_base_ms"] = base_ms
        if self._overlay:
            self._overlay._osc.base_ms = base_ms
            self._overlay._status_lbl.config(text=f"Speed: {label}", fg=YELLOW)

    def _do_overlay(self, fn_name: str):
        """Call a method on the overlay if it exists, else show first."""
        def _run():
            if not self._overlay:
                self._show()
                self.root.after(800, lambda: getattr(self._overlay, fn_name, lambda: None)())
            else:
                getattr(self._overlay, fn_name, lambda: None)()
        self.root.after(0, _run)

    def _rescan_now(self):
        if self._overlay:
            self.root.after(0, self._overlay._rescan)

    def _check_dupes(self):
        """Check for duplicate windows in the scan and report."""
        nodes = scan_windows()
        seen: dict[str, list] = {}
        for n in nodes:
            seen.setdefault(n.title, []).append(n.exe)
        dupes = {t: e for t, e in seen.items() if len(e) > 1}
        if dupes:
            lines = [f"{t[:35]}: {', '.join(e)}" for t, e in list(dupes.items())[:10]]
            msg = f"Duplicates found ({len(dupes)}):\n\n" + "\n".join(lines)
        else:
            flat = flatten(nodes)
            msg = f"No duplicates. {len(nodes)} windows, {len(flat)} total nodes."
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "Branch — Duplicate Check", 0x40)

    def _relaunch(self):
        """Kill self and relaunch fresh."""
        import subprocess
        script = str(SCRIPT_DIR / "windowbranch.py")
        pw     = str(Path(sys.executable).with_name("pythonw.exe"))
        subprocess.Popen([pw, script], creationflags=0x8, cwd=str(SCRIPT_DIR))
        self._quit()

    def _build_tray(self):
        img = PILImage.new("RGBA", (64, 64), (0,0,0,0))
        d   = ImageDraw.Draw(img)
        cx, cy = 32, 12
        d.ellipse([cx-5, cy-5, cx+5, cy+5], fill=BLUE)
        for bx, by, col in [(16, 30, GREEN), (48, 30, PURPLE)]:
            d.line([cx, cy+5, bx, by], fill=col, width=2)
            d.ellipse([bx-5,by-5,bx+5,by+5], fill=col)
            d.line([bx-10,by+14,bx,by+5], fill=col, width=1)
            d.line([bx+10,by+14,bx,by+5], fill=col, width=1)
            d.ellipse([bx-15,by+10,bx-5,by+20], fill=col)
            d.ellipse([bx+5, by+10,bx+15,by+20], fill=col)

        def _af(a, lbl): return lambda: self._set_alpha(a)
        def _sp(ms, lbl): return lambda: self._set_speed(ms, lbl)

        menu = pystray.Menu(
            pystray.MenuItem(f"Branch v{__version__}  ·  Ctrl+Alt+B", None, enabled=False),
            pystray.Menu.SEPARATOR,

            # ── Show / control ──────────────────────────────────────────
            pystray.MenuItem("▶  Show Branch",
                             lambda: self.root.after(0, self._show)),
            pystray.MenuItem("⏸  Pause / Play",
                             lambda: self.root.after(0,
                                 lambda: self._overlay._toggle_pause()
                                 if self._overlay else None)),
            pystray.MenuItem("↻  Re-scan Windows",
                             lambda: self._rescan_now()),
            pystray.MenuItem("✕  Close Overlay",
                             lambda: self.root.after(0,
                                 lambda: self._overlay._close()
                                 if self._overlay else None)),
            pystray.Menu.SEPARATOR,

            # ── Speed presets ────────────────────────────────────────────
            pystray.MenuItem("Speed  ▸", pystray.Menu(
                pystray.MenuItem("🐢  Slow          (8 s)",  _sp(8000,  "Slow")),
                pystray.MenuItem("🚶  Normal        (4 s)",  _sp(4000,  "Normal")),
                pystray.MenuItem("🏃  Fast          (2 s)",  _sp(2000,  "Fast")),
                pystray.MenuItem("⚡  Quick mode    (0.8s)", _sp(800,   "Quick mode")),
                pystray.MenuItem("💀  Ludicrous     (0.3s)", _sp(300,   "Ludicrous")),
            )),

            # ── Opacity presets ──────────────────────────────────────────
            pystray.MenuItem("Opacity  ▸", pystray.Menu(
                pystray.MenuItem("Ghost        (10%)",  _af(0.10, "10%")),
                pystray.MenuItem("Faint        (20%)",  _af(0.20, "20%")),
                pystray.MenuItem("Half         (50%)",  _af(0.50, "50%")),
                pystray.MenuItem("Solid        (85%)",  _af(0.85, "85%")),
                pystray.MenuItem("Full         (95%)",  _af(0.95, "95%")),
            )),

            # ── Presets ──────────────────────────────────────────────────
            pystray.MenuItem("Presets  ▸", pystray.Menu(
                pystray.MenuItem("🗺  Laurence's Every Day  (activate in Branch)",
                                 lambda: self._load_and_activate_laurence()),
                pystray.MenuItem("🎮  Edit in Playground",
                                 lambda: self.root.after(0, self._open_playground)),
                pystray.MenuItem("✕  Clear active preset",
                                 lambda: self.root.after(0, self._clear_tray_preset)),
            )),
            pystray.Menu.SEPARATOR,

            # ── Utilities ────────────────────────────────────────────────
            pystray.MenuItem("Zones overlay",
                             lambda: self._do_overlay("_open_zones")),
            pystray.MenuItem("Settings panel",
                             lambda: self._do_overlay("_open_settings")),
            pystray.MenuItem("Check duplicates",
                             lambda: threading.Thread(
                                 target=self._check_dupes, daemon=True).start()),
            pystray.Menu.SEPARATOR,

            # ── System ───────────────────────────────────────────────────
            pystray.MenuItem("🔄  Relaunch fresh",
                             lambda: threading.Thread(
                                 target=self._relaunch, daemon=True).start()),
            pystray.MenuItem("Quit",  self._quit),
        )
        self._tray_icon = pystray.Icon("branch", img,
                                       f"Branch v{__version__}", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _open_playground(self):
        pg = getattr(self, '_playground', None)
        if pg:
            try: pg.win.lift(); return
            except: self._playground = None
        self._playground = PlaygroundOverlay(self)

    def _load_laurence_preset(self):
        pg = getattr(self, '_playground', None)
        if pg:
            try: pg._load_laurence(); pg.win.lift(); return
            except: self._playground = None
        self._playground = PlaygroundOverlay(self)

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
