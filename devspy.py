"""
Lawrence: Move In — DevSpy v3.0.0
Apple-grade process explorer. PyQt5, exe icons, smooth graphs, system tray.
"""
__version__ = "3.0.0"

import ctypes
import ctypes.wintypes
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil
import win32api
import win32con
import win32gui
import win32process
import win32ui
from PIL import Image as PILImage

from PyQt5.QtCore import (Qt, QTimer, QThread, pyqtSignal, QSize, QRectF,
                           QPointF, QPropertyAnimation, QEasingCurve)
from PyQt5.QtGui import (QIcon, QPixmap, QImage, QPainter, QPainterPath, QColor,
                          QFont, QLinearGradient, QPen, QBrush, QFontMetrics,
                          QCursor)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QLabel, QPushButton, QLineEdit,
                              QTreeWidget, QTreeWidgetItem, QHeaderView,
                              QStackedWidget, QTextEdit, QMenu, QAction,
                              QSystemTrayIcon, QGraphicsDropShadowEffect,
                              QScrollArea, QGridLayout, QFrame, QMessageBox,
                              QSplitter, QSizePolicy, QAbstractItemView)

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "devspy_config.json"

# ── Apple Palette ────────────────────────────────────────────────────────────
BG          = "#f5f5f7"
CARD        = "#ffffff"
TEXT        = "#1d1d1f"
TEXT2       = "#86868b"
TEXT3       = "#aeaeb2"
ACCENT      = "#0071e3"
ACCENT_HOVER= "#0077ED"
DANGER      = "#ff3b30"
SUCCESS     = "#34c759"
ORANGE      = "#ff9500"
PURPLE      = "#af52de"
CYAN        = "#32ade6"
SIDEBAR_BG  = "#f0f0f2"
SIDEBAR_SEL = "#e8e8ed"
BORDER      = "#d2d2d7"
ROW_ALT     = "#fafafa"
SELECT_BG   = "#d4e8fc"
SHADOW      = "#00000018"
STATUS_BG   = "#fbfbfd"

# ── Self-cleanup: kill any old DevSpy instances ──────────────────────────────
def kill_old_instances():
    """Kill any other running devspy.py processes before starting."""
    my_pid = os.getpid()
    killed = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == my_pid:
                continue
            name = (proc.info["name"] or "").lower()
            if "python" not in name:
                continue
            cmdline = proc.info.get("cmdline") or []
            if any("devspy.py" in str(c).lower() for c in cmdline):
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except psutil.TimeoutExpired:
                    proc.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        print(f"[DevSpy] Killed {killed} old instance(s)")
    return killed

# ── Config ───────────────────────────────────────────────────────────────────
def load_config():
    if CONFIG_PATH.exists():
        try: return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except: pass
    return {"always_on_top": False, "geometry": [100, 100, 1060, 680]}

def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

# ── Win32 helpers ────────────────────────────────────────────────────────────
user32 = ctypes.windll.user32

def get_class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value

def get_window_styles(hwnd):
    return user32.GetWindowLongW(hwnd, -16), user32.GetWindowLongW(hwnd, -20)

def is_topmost(hwnd):
    _, ex = get_window_styles(hwnd)
    return bool(ex & 0x8)

def get_cursor_pos():
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def window_from_point(x, y):
    return user32.WindowFromPoint(ctypes.wintypes.POINT(x, y))

def get_all_hwnds_for_pid(pid):
    hwnds = []
    def cb(hwnd, _):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid == pid and win32gui.IsWindow(hwnd): hwnds.append(hwnd)
        except: pass
        return True
    try: win32gui.EnumWindows(cb, None)
    except: pass
    return hwnds

def get_exe_for_pid(pid):
    try:
        h = win32api.OpenProcess(0x0410, False, pid)
        exe = win32process.GetModuleFileNameEx(h, 0)
        win32api.CloseHandle(h)
        return exe
    except:
        try: return psutil.Process(pid).exe()
        except: return ""

# ── Icon extraction & cache ──────────────────────────────────────────────────
# Two caches: raw bytes (thread-safe) and QPixmap (main thread only)
_icon_bytes_cache = {}   # exe_path_lower -> bytes (or None for default)
_icon_pixmap_cache = {}  # exe_path_lower -> QPixmap
_icon_cache_lock = threading.Lock()
_default_pixmap = None
ICON_SIZE = 22

def get_default_icon():
    global _default_pixmap
    if _default_pixmap is None:
        pm = QPixmap(ICON_SIZE, ICON_SIZE)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(ACCENT)))
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.drawRoundedRect(2, 2, ICON_SIZE - 4, ICON_SIZE - 4, 4, 4)
        p.end()
        _default_pixmap = pm
    return _default_pixmap

def _extract_icon_bytes(exe_path):
    """THREAD-SAFE: extract icon as raw RGBA bytes. Returns None if failed."""
    try:
        large, small = win32gui.ExtractIconEx(exe_path, 0)
        if not large:
            return None
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, 32, 32)
        hdc2 = hdc.CreateCompatibleDC()
        hdc2.SelectObject(hbmp)
        hdc2.DrawIcon((0, 0), large[0])
        bmpstr = hbmp.GetBitmapBits(True)
        img = PILImage.frombuffer('RGBA', (32, 32), bmpstr, 'raw', 'BGRA', 0, 1)
        for h in large: win32gui.DestroyIcon(h)
        for h in small: win32gui.DestroyIcon(h)
        hdc2.DeleteDC()
        return img.tobytes("raw", "RGBA")
    except Exception:
        return None

def preload_icons(paths):
    """Called from worker thread — extracts raw bytes for unknown paths."""
    with _icon_cache_lock:
        todo = [p for p in paths if p and p.lower() not in _icon_bytes_cache]
    for path in todo:
        key = path.lower()
        b = _extract_icon_bytes(path)
        with _icon_cache_lock:
            _icon_bytes_cache[key] = b

def get_icon_pixmap(exe_path):
    """MAIN THREAD ONLY: returns cached QPixmap, building from bytes if needed."""
    if not exe_path:
        return get_default_icon()
    key = exe_path.lower()
    if key in _icon_pixmap_cache:
        return _icon_pixmap_cache[key]
    with _icon_cache_lock:
        raw = _icon_bytes_cache.get(key)
    if raw is None:
        # Not preloaded yet or extraction failed — use default for now
        # (worker will extract it on next cycle)
        return get_default_icon()
    try:
        qimg = QImage(raw, 32, 32, QImage.Format_RGBA8888)
        pm = QPixmap.fromImage(qimg).scaled(
            ICON_SIZE, ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        _icon_pixmap_cache[key] = pm
        return pm
    except Exception:
        return get_default_icon()

# ── GPU info (PowerShell) ────────────────────────────────────────────────────
def get_gpu_info():
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object Name | ConvertTo-Json"],
            capture_output=True, text=True, timeout=5, creationflags=0x08000000)
        d = json.loads(r.stdout)
        return [d] if isinstance(d, dict) else d
    except: return []


# ═════════════════════════════════════════════════════════════════════════════
#  WORKER THREADS
# ═════════════════════════════════════════════════════════════════════════════
class ProcWorker(QThread):
    updated = pyqtSignal(list)
    icons_ready = pyqtSignal()
    def run(self):
        while True:
            procs = []
            paths = set()
            for p in psutil.process_iter(["pid","name","cpu_percent","memory_info","status","exe"]):
                try:
                    i = p.info
                    mem = (i["memory_info"].rss / (1024*1024)) if i.get("memory_info") else 0
                    path = i.get("exe") or ""
                    procs.append({"pid":i["pid"], "name":i["name"] or "—",
                                  "cpu":i.get("cpu_percent",0) or 0,
                                  "mem":round(mem,1), "status":i.get("status","?"),
                                  "path":path})
                    if path:
                        paths.add(path)
                except: pass
            self.updated.emit(procs)
            # Preload icons for this batch (on bg thread, Win32 calls only)
            preload_icons(list(paths))
            self.icons_ready.emit()
            time.sleep(2.5)

class SysWorker(QThread):
    updated = pyqtSignal(dict)
    def run(self):
        prev_disk = psutil.disk_io_counters()
        prev_net = psutil.net_io_counters()
        prev_t = time.time()
        while True:
            now = time.time()
            dt = max(now - prev_t, 0.1)
            cpu = psutil.cpu_percent(interval=0)
            cores = psutil.cpu_percent(interval=0, percpu=True)
            mem = psutil.virtual_memory()
            disk = psutil.disk_io_counters()
            net = psutil.net_io_counters()
            dr = (disk.read_bytes - prev_disk.read_bytes) / dt
            dw = (disk.write_bytes - prev_disk.write_bytes) / dt
            ns = (net.bytes_sent - prev_net.bytes_sent) / dt
            nr = (net.bytes_recv - prev_net.bytes_recv) / dt
            prev_disk, prev_net, prev_t = disk, net, now
            boot = datetime.fromtimestamp(psutil.boot_time())
            up = datetime.now() - boot
            hrs, rem = divmod(int(up.total_seconds()), 3600)
            mins, secs = divmod(rem, 60)
            self.updated.emit({
                "cpu": cpu, "cores": cores, "mem_pct": mem.percent,
                "mem_total": mem.total, "mem_used": mem.used,
                "disk_r": dr, "disk_w": dw, "net_s": ns, "net_r": nr,
                "uptime": f"{hrs}:{mins:02d}:{secs:02d}",
                "uptime_full": f"Since {boot:%Y-%m-%d %H:%M} ({hrs}h {mins}m)",
                "n_cores": psutil.cpu_count(logical=False),
            })
            time.sleep(1.0)


# ═════════════════════════════════════════════════════════════════════════════
#  CUSTOM WIDGETS
# ═════════════════════════════════════════════════════════════════════════════

class Card(QFrame):
    """White card with rounded corners and subtle shadow."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            Card {{ background: {CARD}; border-radius: 12px; border: 1px solid {BORDER}; }}
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)


class PerfGraph(QWidget):
    """Smooth CPU/Memory graph with gradient fill — Apple aesthetic."""
    def __init__(self, color=ACCENT, parent=None):
        super().__init__(parent)
        self._data = []
        self._color = QColor(color)
        self.setMinimumHeight(180)

    def set_data(self, data):
        self._data = data[-60:]
        self.update()

    def paintEvent(self, event):
        if not self._data or len(self._data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        margin = 1

        # Background
        p.fillRect(0, 0, w, h, QColor(CARD))

        # Grid
        pen = QPen(QColor(BORDER), 0.5, Qt.DotLine)
        p.setPen(pen)
        for i in range(1, 5):
            y = margin + (h - 2*margin) * i / 5
            p.drawLine(0, int(y), w, int(y))

        # Build path
        n = len(self._data)
        path = QPainterPath()
        fill_path = QPainterPath()

        def pt(i, v):
            x = margin + (w - 2*margin) * i / (n - 1)
            y = margin + (h - 2*margin) * (1 - v / 100.0)
            return QPointF(x, y)

        path.moveTo(pt(0, self._data[0]))
        fill_path.moveTo(QPointF(margin, h - margin))
        fill_path.lineTo(pt(0, self._data[0]))

        for i in range(1, n):
            path.lineTo(pt(i, self._data[i]))
            fill_path.lineTo(pt(i, self._data[i]))

        fill_path.lineTo(QPointF(w - margin, h - margin))
        fill_path.closeSubpath()

        # Gradient fill
        grad = QLinearGradient(0, 0, 0, h)
        c = QColor(self._color)
        c.setAlpha(60)
        grad.setColorAt(0, c)
        c.setAlpha(5)
        grad.setColorAt(1, c)
        p.fillPath(fill_path, QBrush(grad))

        # Line
        p.setPen(QPen(self._color, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)

        # Current value label
        val = self._data[-1]
        p.setPen(QColor(TEXT))
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.drawText(QRectF(w - 80, 6, 74, 24), Qt.AlignRight | Qt.AlignTop, f"{val:.0f}%")

        p.end()


class SidebarButton(QPushButton):
    """Apple-style sidebar tab button."""
    def __init__(self, text, icon_char="", parent=None):
        super().__init__(parent)
        self.setText(f"  {icon_char}   {text}" if icon_char else f"  {text}")
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT}; border: none;
                border-radius: 8px; font: 13px 'Segoe UI'; text-align: left;
                padding-left: 12px;
            }}
            QPushButton:checked {{
                background: {SIDEBAR_SEL}; color: {ACCENT}; font-weight: 600;
            }}
            QPushButton:hover:!checked {{
                background: #e8e8ea;
            }}
        """)


class CopyBtn(QPushButton):
    """Small 'Copy' pill button — Apple style."""
    def __init__(self, text="Copy", parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(24)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {BG}; color: {ACCENT}; border: 1px solid {BORDER};
                border-radius: 6px; font: 11px 'Segoe UI'; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {SELECT_BG}; }}
            QPushButton:pressed {{ background: {ACCENT}; color: white; }}
        """)


class ActionBtn(QPushButton):
    """Bottom-bar action button."""
    def __init__(self, text, danger=False, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(30)
        self.setCursor(Qt.PointingHandCursor)
        bg = DANGER if danger else ACCENT
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: white; border: none;
                border-radius: 6px; font: 12px 'Segoe UI Semibold'; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {ACCENT_HOVER if not danger else '#e0342b'}; }}
        """)


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═════════════════════════════════════════════════════════════════════════════
class DevSpyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self._proc_cache = []
        self._selected_pid = None
        self._sort_col = "cpu"
        self._sort_rev = True
        self._cpu_history = []
        self._mem_history = []
        self._spy_active = True
        self._spy_pinned = False
        self._ids_data = {}

        self._init_ui()
        self._init_tray()
        self._init_workers()
        self._init_hotkey()

    # ═══ UI ══════════════════════════════════════════════════════════════════
    def _init_ui(self):
        self.setWindowTitle("DevSpy")
        geo = self.cfg.get("geometry", [100, 100, 1060, 680])
        self.setGeometry(*geo)
        self.setMinimumSize(800, 500)
        if self.cfg.get("always_on_top"):
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet(f"background: {BG};")
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"background: {SIDEBAR_BG}; border-right: 1px solid {BORDER};")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(8, 16, 8, 8)
        sb_layout.setSpacing(2)

        # Logo
        logo = QLabel("DevSpy")
        logo.setStyleSheet(f"color: {ACCENT}; font: bold 18px 'Segoe UI'; border: none; padding-bottom: 12px;")
        sb_layout.addWidget(logo)

        self._sidebar_btns = []
        tabs = [
            ("\U0001F4CB", "Processes"),
            ("\U0001F4C8", "Performance"),
            ("\U0001F50D", "Details"),
            ("\U0001F5D4", "Window Spy"),
            ("\U00002699", "System"),
        ]
        for icon, name in tabs:
            btn = SidebarButton(name, icon)
            btn.clicked.connect(lambda checked, n=name: self._switch_tab(n))
            sb_layout.addWidget(btn)
            self._sidebar_btns.append((name, btn))

        sb_layout.addStretch()
        ver = QLabel(f"v{__version__}")
        ver.setStyleSheet(f"color: {TEXT3}; font: 10px 'Segoe UI'; border: none;")
        sb_layout.addWidget(ver)

        main_layout.addWidget(sidebar)

        # ── Content stack ────────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet(f"background: {BG};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._stack = QStackedWidget()
        right_layout.addWidget(self._stack)

        # Status bar
        self._status_bar = QLabel("  DevSpy v3.0.0")
        self._status_bar.setFixedHeight(26)
        self._status_bar.setStyleSheet(f"""
            background: {STATUS_BG}; color: {TEXT2}; font: 11px 'Segoe UI';
            border-top: 1px solid {BORDER}; padding-left: 8px;
        """)
        right_layout.addWidget(self._status_bar)

        main_layout.addWidget(right)

        # Build pages
        self._build_processes_page()
        self._build_performance_page()
        self._build_details_page()
        self._build_spy_page()
        self._build_system_page()

        # Select first tab
        self._switch_tab("Processes")

    def _switch_tab(self, name):
        idx_map = {"Processes": 0, "Performance": 1, "Details": 2, "Window Spy": 3, "System": 4}
        idx = idx_map.get(name, 0)
        self._stack.setCurrentIndex(idx)
        for n, btn in self._sidebar_btns:
            btn.setChecked(n == name)

    # ═══ Processes Page ══════════════════════════════════════════════════════
    def _build_processes_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(10)

        # Title + search
        top = QHBoxLayout()
        title = QLabel("Processes")
        title.setStyleSheet(f"color: {TEXT}; font: bold 22px 'Segoe UI'; background: transparent;")
        top.addWidget(title)
        top.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search processes...")
        self._search.setFixedSize(260, 32)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {CARD}; border: 1px solid {BORDER}; border-radius: 16px;
                padding: 0 14px; font: 13px 'Segoe UI'; color: {TEXT};
            }}
            QLineEdit:focus {{ border-color: {ACCENT}; }}
        """)
        self._search.textChanged.connect(self._render_procs)
        top.addWidget(self._search)
        layout.addLayout(top)

        # Tree
        self._proc_tree = QTreeWidget()
        self._proc_tree.setHeaderLabels(["", "Name", "PID", "CPU", "Memory", "Status"])
        self._proc_tree.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._proc_tree.setColumnWidth(0, 34)  # icon
        self._proc_tree.setColumnWidth(1, 200)
        self._proc_tree.setColumnWidth(2, 65)
        self._proc_tree.setColumnWidth(3, 65)
        self._proc_tree.setColumnWidth(4, 85)
        self._proc_tree.setColumnWidth(5, 80)
        self._proc_tree.setRootIsDecorated(False)
        self._proc_tree.setAlternatingRowColors(True)
        self._proc_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self._proc_tree.setSortingEnabled(False)
        self._proc_tree.header().setStretchLastSection(True)
        self._proc_tree.header().sectionClicked.connect(self._on_header_click)
        self._proc_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._proc_tree.customContextMenuRequested.connect(self._proc_context_menu)
        self._proc_tree.itemSelectionChanged.connect(self._on_proc_select)
        self._proc_tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px;
                font: 12px 'Segoe UI'; color: {TEXT}; outline: 0;
            }}
            QTreeWidget::item {{ height: 28px; padding: 2px 4px; }}
            QTreeWidget::item:alternate {{ background: {ROW_ALT}; }}
            QTreeWidget::item:selected {{ background: {SELECT_BG}; color: {TEXT}; }}
            QTreeWidget::item:hover:!selected {{ background: #eef3fb; }}
            QHeaderView::section {{
                background: {BG}; color: {TEXT2}; border: none;
                border-bottom: 1px solid {BORDER}; font: 11px 'Segoe UI Semibold';
                padding: 6px 8px;
            }}
        """)
        layout.addWidget(self._proc_tree)

        # Bottom buttons
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        for label, slot in [("Copy PID", lambda: self._copy_field("pid")),
                             ("Copy Path", lambda: self._copy_field("path")),
                             ("Copy CmdLine", lambda: self._copy_field("cmdline")),
                             ("Copy JSON", self._copy_proc_json),
                             ("Open Location", self._open_proc_location)]:
            b = CopyBtn(label)
            b.setFixedWidth(95)
            b.clicked.connect(slot)
            bottom.addWidget(b)
        bottom.addStretch()
        end_btn = ActionBtn("End Task", danger=True)
        end_btn.clicked.connect(self._kill_proc)
        bottom.addWidget(end_btn)
        layout.addLayout(bottom)

        # Context menu
        self._proc_menu = QMenu(self)
        self._proc_menu.setStyleSheet(f"""
            QMenu {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px;
                     font: 12px 'Segoe UI'; color: {TEXT}; padding: 4px; }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {SELECT_BG}; }}
            QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
        """)
        for label, slot in [("End task", self._kill_proc), (None, None),
                             ("Open file location", self._open_proc_location), (None, None),
                             ("Copy — PID", lambda: self._copy_field("pid")),
                             ("Copy — Name", lambda: self._copy_field("name")),
                             ("Copy — Path", lambda: self._copy_field("path")),
                             ("Copy — Command line", lambda: self._copy_field("cmdline")),
                             ("Copy — as JSON", self._copy_proc_json), (None, None),
                             ("Go to Details", self._goto_details)]:
            if label is None:
                self._proc_menu.addSeparator()
            else:
                a = self._proc_menu.addAction(label)
                a.triggered.connect(slot)

        self._stack.addWidget(page)

    # ═══ Performance Page ════════════════════════════════════════════════════
    def _build_performance_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(12)

        title = QLabel("Performance")
        title.setStyleSheet(f"color: {TEXT}; font: bold 22px 'Segoe UI'; background: transparent;")
        layout.addWidget(title)

        # CPU Graph card
        cpu_card = Card()
        cpu_layout = QVBoxLayout(cpu_card)
        cpu_layout.setContentsMargins(16, 12, 16, 12)

        cpu_head = QHBoxLayout()
        cpu_lbl = QLabel("CPU")
        cpu_lbl.setStyleSheet(f"color: {TEXT}; font: bold 15px 'Segoe UI'; background: transparent; border: none;")
        cpu_head.addWidget(cpu_lbl)
        self._cpu_name_lbl = QLabel("")
        self._cpu_name_lbl.setStyleSheet(f"color: {TEXT2}; font: 11px 'Segoe UI'; background: transparent; border: none;")
        cpu_head.addWidget(self._cpu_name_lbl)
        cpu_head.addStretch()
        cpu_layout.addLayout(cpu_head)

        self._cpu_graph = PerfGraph(ACCENT)
        cpu_layout.addWidget(self._cpu_graph)
        layout.addWidget(cpu_card)

        # Memory graph card
        mem_card = Card()
        mem_layout = QVBoxLayout(mem_card)
        mem_layout.setContentsMargins(16, 12, 16, 12)
        mem_lbl = QLabel("Memory")
        mem_lbl.setStyleSheet(f"color: {TEXT}; font: bold 15px 'Segoe UI'; background: transparent; border: none;")
        mem_layout.addWidget(mem_lbl)
        self._mem_graph = PerfGraph(PURPLE)
        self._mem_graph.setMinimumHeight(120)
        mem_layout.addWidget(self._mem_graph)
        layout.addWidget(mem_card)

        # Stats grid
        stats_card = Card()
        stats_grid = QGridLayout(stats_card)
        stats_grid.setContentsMargins(16, 12, 16, 12)
        stats_grid.setSpacing(8)
        self._perf_stats = {}
        items = [("Utilisation","util"),("Processes","procs"),("Threads","threads"),
                 ("Up time","uptime"),("Cores","cores"),("CPU Speed","speed")]
        for i, (label, key) in enumerate(items):
            r, c = divmod(i, 3)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {TEXT2}; font: 10px 'Segoe UI'; background: transparent; border: none;")
            stats_grid.addWidget(lbl, r*2, c)
            var = QLabel("—")
            var.setStyleSheet(f"color: {TEXT}; font: bold 14px 'Segoe UI'; background: transparent; border: none;")
            stats_grid.addWidget(var, r*2+1, c)
            self._perf_stats[key] = var
        layout.addWidget(stats_card)

        layout.addStretch()
        self._stack.addWidget(page)

        # Async fetchers
        threading.Thread(target=self._fetch_cpu_name, daemon=True).start()
        threading.Thread(target=self._fetch_gpu_info, daemon=True).start()

    # ═══ Details Page ════════════════════════════════════════════════════════
    def _build_details_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Details")
        title.setStyleSheet(f"color: {TEXT}; font: bold 22px 'Segoe UI'; background: transparent;")
        top.addWidget(title)
        top.addStretch()
        load_btn = ActionBtn("Load Details")
        load_btn.clicked.connect(self._refresh_ids)
        top.addWidget(load_btn)
        copy_btn = CopyBtn("Copy All (JSON)")
        copy_btn.setFixedWidth(120)
        copy_btn.clicked.connect(self._copy_ids_json)
        top.addWidget(copy_btn)
        layout.addLayout(top)

        self._ids_text = QTextEdit()
        self._ids_text.setReadOnly(True)
        self._ids_text.setStyleSheet(f"""
            QTextEdit {{
                background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px;
                font: 11px 'Consolas'; color: {TEXT}; padding: 12px;
            }}
        """)
        self._ids_text.setPlainText("Select a process in Processes, then click Load Details.")
        layout.addWidget(self._ids_text)
        self._stack.addWidget(page)

    # ═══ Window Spy Page ═════════════════════════════════════════════════════
    def _build_spy_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Window Spy")
        title.setStyleSheet(f"color: {TEXT}; font: bold 22px 'Segoe UI'; background: transparent;")
        top.addWidget(title)
        top.addStretch()
        self._spy_btn = ActionBtn("Active")
        self._spy_btn.clicked.connect(self._toggle_spy)
        top.addWidget(self._spy_btn)
        self._pin_btn = CopyBtn("Pin: Off")
        self._pin_btn.setFixedWidth(70)
        self._pin_btn.clicked.connect(self._toggle_pin)
        top.addWidget(self._pin_btn)
        copy_all = CopyBtn("Copy All (JSON)")
        copy_all.setFixedWidth(120)
        copy_all.clicked.connect(self._copy_spy_all)
        top.addWidget(copy_all)
        layout.addLayout(top)

        card = Card()
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 16, 20, 16)
        grid.setSpacing(6)
        grid.setColumnStretch(1, 1)

        self._spy_fields = {}
        fields = [("Title","title"),("Class","class"),("HWND","hwnd"),
                  ("PID","pid"),("Exe","exe"),("Path","path"),
                  ("Rect","rect"),("Size","size"),("Style","style"),
                  ("ExStyle","exstyle"),("Visible","visible"),
                  ("Topmost","topmost"),("Parent HWND","parent")]
        for i, (label, key) in enumerate(fields):
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(f"color: {TEXT2}; font: bold 11px 'Segoe UI'; background: transparent; border: none;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(lbl, i, 0)
            val = QLabel("—")
            val.setStyleSheet(f"color: {TEXT}; font: 12px 'Consolas'; background: transparent; border: none;")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(val, i, 1)
            btn = CopyBtn()
            btn.setFixedWidth(50)
            btn.clicked.connect(lambda _, v=val: self._clip(v.text()))
            grid.addWidget(btn, i, 2)
            self._spy_fields[key] = val

        layout.addWidget(card)
        layout.addStretch()
        self._stack.addWidget(page)

    # ═══ System Page ═════════════════════════════════════════════════════════
    def _build_system_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(10)

        title = QLabel("System")
        title.setStyleSheet(f"color: {TEXT}; font: bold 22px 'Segoe UI'; background: transparent;")
        layout.addWidget(title)

        card = Card()
        grid = QGridLayout(card)
        grid.setContentsMargins(20, 16, 20, 16)
        grid.setSpacing(6)
        grid.setColumnStretch(1, 1)

        self._sys_fields = {}
        rows = [("OS","os"),("Hostname","hostname"),("User","user"),
                ("Uptime","uptime"),("Python","python"),
                (None, None),
                ("CPU","cpu_name"),("CPU Usage","cpu_pct"),("Per-Core","cpu_cores"),
                (None, None),
                ("RAM Total","ram_total"),("RAM Used","ram_used"),("RAM %","ram_pct"),
                (None, None),
                ("Disk Read/s","disk_r"),("Disk Write/s","disk_w"),
                ("Net Sent/s","net_s"),("Net Recv/s","net_r"),
                (None, None),
                ("GPU","gpu")]
        ri = 0
        for label, key in rows:
            if key is None:
                sep = QFrame()
                sep.setFixedHeight(1)
                sep.setStyleSheet(f"background: {BORDER}; border: none;")
                grid.addWidget(sep, ri, 0, 1, 3)
                ri += 1
                continue
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(f"color: {TEXT2}; font: bold 11px 'Segoe UI'; background: transparent; border: none;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(lbl, ri, 0)
            val = QLabel("—")
            val.setStyleSheet(f"color: {TEXT}; font: 12px 'Consolas'; background: transparent; border: none;")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(val, ri, 1)
            btn = CopyBtn()
            btn.setFixedWidth(50)
            btn.clicked.connect(lambda _, v=val: self._clip(v.text()))
            grid.addWidget(btn, ri, 2)
            self._sys_fields[key] = val
            ri += 1

        scroll = QScrollArea()
        scroll.setWidget(card)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        layout.addWidget(scroll)

        # Static values
        self._sys_fields["os"].setText(f"{platform.system()} {platform.release()} ({platform.version()})")
        self._sys_fields["hostname"].setText(platform.node())
        self._sys_fields["user"].setText(os.getlogin())
        self._sys_fields["python"].setText(f"{platform.python_version()} ({sys.executable})")

        self._stack.addWidget(page)

    # ═══ Workers ═════════════════════════════════════════════════════════════
    def _init_workers(self):
        self._proc_worker = ProcWorker()
        self._proc_worker.updated.connect(self._on_procs)
        self._proc_worker.icons_ready.connect(self._render_procs)
        self._proc_worker.start()

        self._sys_worker = SysWorker()
        self._sys_worker.updated.connect(self._on_sys)
        self._sys_worker.start()

        self._spy_timer = QTimer()
        self._spy_timer.timeout.connect(self._poll_spy)
        self._spy_timer.start(100)

    def _on_procs(self, procs):
        self._proc_cache = procs
        self._render_procs()

    def _render_procs(self):
        tree = self._proc_tree
        filt = self._search.text().lower()

        # Remember selection
        sel_pid = None
        sel = tree.currentItem()
        if sel:
            try: sel_pid = int(sel.text(2))
            except: pass

        data = self._proc_cache
        if filt:
            data = [p for p in data if filt in p["name"].lower()
                    or filt in str(p["pid"]) or filt in p.get("path","").lower()]

        key = self._sort_col
        num = key in ("cpu","mem","pid")
        data = sorted(data, key=lambda p: p.get(key, 0) if num else str(p.get(key,"")).lower(),
                       reverse=self._sort_rev)

        tree.setUpdatesEnabled(False)
        tree.clear()
        reselect = None
        for p in data:
            item = QTreeWidgetItem()
            icon_pm = get_icon_pixmap(p.get("path"))
            item.setIcon(0, QIcon(icon_pm))
            item.setText(1, p["name"])
            item.setText(2, str(p["pid"]))
            item.setText(3, f"{p['cpu']:.1f}%")
            item.setText(4, f"{p['mem']:.1f} MB")
            st = p["status"].capitalize() if p["status"] != "running" else "Running"
            item.setText(5, st)
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
            tree.addTopLevelItem(item)
            if sel_pid and p["pid"] == sel_pid:
                reselect = item

        tree.setUpdatesEnabled(True)
        if reselect:
            tree.setCurrentItem(reselect)

        self._status_bar.setText(f"  {len(data)} processes   |   DevSpy v{__version__}")

    def _on_header_click(self, col):
        col_map = {1:"name", 2:"pid", 3:"cpu", 4:"mem", 5:"status"}
        key = col_map.get(col)
        if not key: return
        if self._sort_col == key:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = key
            self._sort_rev = key in ("cpu","mem","pid")
        self._render_procs()

    def _on_sys(self, d):
        # Performance graphs
        self._cpu_history.append(d["cpu"])
        self._mem_history.append(d["mem_pct"])
        self._cpu_history = self._cpu_history[-60:]
        self._mem_history = self._mem_history[-60:]
        self._cpu_graph.set_data(self._cpu_history)
        self._mem_graph.set_data(self._mem_history)

        # Perf stats
        ps = self._perf_stats
        ps["util"].setText(f"{d['cpu']:.0f}%")
        ps["procs"].setText(str(len(self._proc_cache)))
        ps["threads"].setText("—")
        ps["uptime"].setText(d["uptime"])
        ps["cores"].setText(str(d["n_cores"]))

        # System tab
        sf = self._sys_fields
        sf["cpu_pct"].setText(f"{d['cpu']:.1f}%")
        sf["cpu_cores"].setText("  ".join(f"{c:.0f}%" for c in d["cores"]))
        sf["ram_total"].setText(f"{d['mem_total']/(1024**3):.1f} GB")
        sf["ram_used"].setText(f"{d['mem_used']/(1024**3):.1f} GB")
        sf["ram_pct"].setText(f"{d['mem_pct']}%")
        sf["disk_r"].setText(f"{d['disk_r']/(1024**2):.1f} MB/s")
        sf["disk_w"].setText(f"{d['disk_w']/(1024**2):.1f} MB/s")
        sf["net_s"].setText(f"{d['net_s']/1024:.1f} KB/s")
        sf["net_r"].setText(f"{d['net_r']/1024:.1f} KB/s")
        sf["uptime"].setText(d["uptime_full"])

        # Status bar
        self._status_bar.setText(
            f"  {len(self._proc_cache)} processes  |  CPU {d['cpu']:.0f}%  |  "
            f"Memory {d['mem_pct']:.0f}%  |  DevSpy v{__version__}")

    # ═══ Process Actions ═════════════════════════════════════════════════════
    def _get_selected_proc(self):
        item = self._proc_tree.currentItem()
        if not item: return None
        pid = int(item.text(2))
        for p in self._proc_cache:
            if p["pid"] == pid: return p
        return {"pid": pid, "name": item.text(1), "path": "", "cmdline": ""}

    def _on_proc_select(self):
        p = self._get_selected_proc()
        if p: self._selected_pid = p["pid"]

    def _proc_context_menu(self, pos):
        item = self._proc_tree.itemAt(pos)
        if item:
            self._proc_tree.setCurrentItem(item)
            self._on_proc_select()
            self._proc_menu.exec_(self._proc_tree.viewport().mapToGlobal(pos))

    def _copy_field(self, field):
        p = self._get_selected_proc()
        if not p: return
        if field == "cmdline" and not p.get("cmdline"):
            try: p["cmdline"] = " ".join(psutil.Process(p["pid"]).cmdline())
            except: p["cmdline"] = ""
        if field == "path" and not p.get("path"):
            p["path"] = get_exe_for_pid(p["pid"])
        self._clip(str(p.get(field, "")))

    def _copy_proc_json(self):
        p = self._get_selected_proc()
        if p: self._clip(json.dumps(p, indent=2))

    def _open_proc_location(self):
        p = self._get_selected_proc()
        if p and p.get("path"):
            subprocess.Popen(["explorer", "/select,", p["path"]], creationflags=0x8)

    def _kill_proc(self):
        p = self._get_selected_proc()
        if not p: return
        if QMessageBox.question(self, "End task",
                f"End '{p.get('name','')}' (PID {p['pid']})?") == QMessageBox.Yes:
            try: psutil.Process(p["pid"]).terminate()
            except: pass

    def _goto_details(self):
        self._switch_tab("Details")
        self._refresh_ids()

    # ═══ Details ═════════════════════════════════════════════════════════════
    def _refresh_ids(self):
        pid = self._selected_pid
        if not pid:
            self._ids_text.setPlainText("No process selected.")
            return
        threading.Thread(target=self._collect_ids, args=(pid,), daemon=True).start()

    def _collect_ids(self, pid):
        d = {"pid": pid}
        try:
            p = psutil.Process(pid)
            d["name"] = p.name(); d["ppid"] = p.ppid(); d["status"] = p.status()
            d["exe"] = p.exe(); d["cmdline"] = p.cmdline()
            d["create_time"] = datetime.fromtimestamp(p.create_time()).isoformat()
            try: d["username"] = p.username()
            except: d["username"] = "—"
            try: d["cwd"] = p.cwd()
            except: d["cwd"] = "—"
            try:
                d["num_threads"] = p.num_threads()
                d["thread_ids"] = [t.id for t in p.threads()[:50]]
            except: d["thread_ids"] = []
            try:
                d["connections"] = [{"laddr":str(c.laddr),"raddr":str(c.raddr),"status":c.status}
                                    for c in p.net_connections()[:20]]
            except: d["connections"] = []
            try: d["environ"] = dict(list(p.environ().items())[:40])
            except: d["environ"] = {}
            try:
                mi = p.memory_info()
                d["memory_info"] = {"rss_mb":round(mi.rss/(1024**2),1),"vms_mb":round(mi.vms/(1024**2),1)}
            except: pass
        except Exception as e:
            d["error"] = str(e)

        hwnds = get_all_hwnds_for_pid(pid)
        d["window_handles"] = [{"hwnd":f"0x{h:08X}","title":win32gui.GetWindowText(h),
                                 "class":get_class_name(h),"visible":bool(win32gui.IsWindowVisible(h))}
                                for h in hwnds[:30]]
        self._ids_data = d
        QTimer.singleShot(0, self._render_ids)

    def _render_ids(self):
        d = self._ids_data
        lines = []
        def section(t): lines.append(f"\n{'='*50}\n  {t}\n{'='*50}")
        def kv(k, v): lines.append(f"  {k}: {v}")

        section("PROCESS")
        for k in ["pid","ppid","name","status","username","exe","cwd","create_time","num_threads"]:
            if k in d: kv(k.upper(), d[k])
        if d.get("cmdline"): kv("CMDLINE", " ".join(d["cmdline"]))
        if d.get("memory_info"):
            section("MEMORY")
            for k, v in d["memory_info"].items(): kv(k, v)
        if d.get("thread_ids"):
            section("THREAD IDs")
            lines.append(f"  {', '.join(str(x) for x in d['thread_ids'])}")
        if d.get("window_handles"):
            section("WINDOW HANDLES")
            for wh in d["window_handles"]:
                vis = "visible" if wh["visible"] else "hidden"
                lines.append(f"  {wh['hwnd']}  {wh['class']}  [{vis}]  {wh['title'][:60]}")
        if d.get("connections"):
            section("NETWORK CONNECTIONS")
            for c in d["connections"]:
                lines.append(f"  {c['laddr']} -> {c['raddr']}  [{c['status']}]")
        if d.get("environ"):
            section("ENVIRONMENT")
            for k, v in d["environ"].items():
                lines.append(f"  {k}={v[:120]}")
        self._ids_text.setPlainText("\n".join(lines))

    def _copy_ids_json(self):
        if self._ids_data:
            self._clip(json.dumps(self._ids_data, indent=2, default=str))

    # ═══ Window Spy ══════════════════════════════════════════════════════════
    def _poll_spy(self):
        # Slow down when not on spy tab
        current = self._stack.currentIndex()
        if current != 3:
            self._spy_timer.setInterval(1000)
        else:
            self._spy_timer.setInterval(100)

        if not self._spy_active or self._spy_pinned or current != 3:
            return
        try:
            x, y = get_cursor_pos()
            hwnd = window_from_point(x, y)
            if hwnd:
                title = win32gui.GetWindowText(hwnd)
                cls = get_class_name(hwnd)
                rect = win32gui.GetWindowRect(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                exe = get_exe_for_pid(pid)
                style, exstyle = get_window_styles(hwnd)
                visible = win32gui.IsWindowVisible(hwnd)
                top = is_topmost(hwnd)
                parent = win32gui.GetParent(hwnd)

                sf = self._spy_fields
                sf["title"].setText(title or "(none)")
                sf["class"].setText(cls)
                sf["hwnd"].setText(f"0x{hwnd:08X}  ({hwnd})")
                sf["pid"].setText(str(pid))
                sf["exe"].setText(os.path.basename(exe) if exe else "—")
                sf["path"].setText(exe or "—")
                sf["rect"].setText(f"L:{rect[0]}  T:{rect[1]}  R:{rect[2]}  B:{rect[3]}")
                sf["size"].setText(f"{rect[2]-rect[0]} x {rect[3]-rect[1]}")
                sf["style"].setText(f"0x{style:08X}")
                sf["exstyle"].setText(f"0x{exstyle:08X}")
                sf["visible"].setText("Yes" if visible else "No")
                sf["topmost"].setText("Yes" if top else "No")
                sf["parent"].setText(f"0x{parent:08X}" if parent else "None")
        except: pass

    def _toggle_spy(self):
        self._spy_active = not self._spy_active
        self._spy_btn.setText("Active" if self._spy_active else "Paused")

    def _toggle_pin(self):
        self._spy_pinned = not self._spy_pinned
        self._pin_btn.setText(f"Pin: {'On' if self._spy_pinned else 'Off'}")

    def _copy_spy_all(self):
        data = {k: v.text() for k, v in self._spy_fields.items()}
        self._clip(json.dumps(data, indent=2))

    # ═══ Async fetchers ══════════════════════════════════════════════════════
    def _fetch_cpu_name(self):
        try:
            r = subprocess.run(["powershell","-NoProfile","-Command",
                "(Get-CimInstance Win32_Processor).Name"],
                capture_output=True, text=True, timeout=5, creationflags=0x08000000)
            name = r.stdout.strip()
            if name:
                QTimer.singleShot(0, lambda: (
                    self._cpu_name_lbl.setText(name),
                    self._sys_fields["cpu_name"].setText(name),
                    self._perf_stats["speed"].setText(
                        name.split("@")[-1].strip() if "@" in name else "—")))
        except: pass

    def _fetch_gpu_info(self):
        gpus = get_gpu_info()
        if gpus:
            name = gpus[0].get("Name", "—")
            QTimer.singleShot(0, lambda: self._sys_fields["gpu"].setText(name))

    # ═══ System Tray ═════════════════════════════════════════════════════════
    def _init_tray(self):
        # Build icon
        pm = QPixmap(32, 32)
        pm.fill(QColor(ACCENT))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor("#ffffff"))
        p.setFont(QFont("Segoe UI", 14, QFont.Bold))
        p.drawText(QRectF(0, 0, 32, 32), Qt.AlignCenter, "D")
        p.end()

        self._tray = QSystemTrayIcon(QIcon(pm), self)
        tray_menu = QMenu()
        tray_menu.addAction("Show / Hide", self._toggle_visibility)
        self._aot_action = tray_menu.addAction("Always on top")
        self._aot_action.setCheckable(True)
        self._aot_action.setChecked(self.cfg.get("always_on_top", False))
        self._aot_action.triggered.connect(self._toggle_aot)
        tray_menu.addSeparator()
        tray_menu.addAction("Quit DevSpy", self._quit)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(lambda reason: self._toggle_visibility()
                                      if reason == QSystemTrayIcon.DoubleClick else None)
        self._tray.show()

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _toggle_aot(self):
        val = self._aot_action.isChecked()
        self.cfg["always_on_top"] = val
        save_config(self.cfg)
        flags = self.windowFlags()
        if val:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    def _quit(self):
        self._tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    # ═══ Hotkey ══════════════════════════════════════════════════════════════
    def _init_hotkey(self):
        self._hk_timer = QTimer()
        self._hk_timer.timeout.connect(self._check_hotkey)
        self._hk_timer.start(50)
        self._hk_cooldown = 0

    def _check_hotkey(self):
        if self._hk_cooldown > 0:
            self._hk_cooldown -= 1
            return
        try:
            if (user32.GetAsyncKeyState(0x11) & 0x8000 and
                user32.GetAsyncKeyState(0x10) & 0x8000 and
                user32.GetAsyncKeyState(0x44) & 0x8000):
                self._toggle_visibility()
                self._hk_cooldown = 8  # ~400ms cooldown
        except: pass

    # ═══ Clipboard ═══════════════════════════════════════════════════════════
    def _clip(self, text):
        QApplication.clipboard().setText(text)
        old = self._status_bar.text()
        self._status_bar.setText("  Copied to clipboard!")
        QTimer.singleShot(1500, lambda: self._status_bar.setText(old))


# ═════════════════════════════════════════════════════════════════════════════
def main():
    kill_old_instances()
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)  # Keep running when hidden to tray
    win = DevSpyWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
