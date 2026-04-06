"""
Lawrence: Move In — TrayClick helper
System tray icon with REAL click support using win32gui (pywin32).
Bypasses pystray entirely because default_action doesn't fire on Windows 10.

Usage:
    from trayclick import TrayIcon
    icon = TrayIcon("My App", pil_image,
        menu=[("Label", callback), None, ("Quit", quit_fn)],
        on_click=single_click_fn,
        on_dblclick=double_click_fn)
    icon.run()   # blocking, use threading
    icon.stop()
"""

import os, sys, tempfile, threading, time
from pathlib import Path

import win32api, win32con, win32gui
from PIL import Image

WM_USER    = 0x0400
WM_TRAY    = WM_USER + 77
IDI_APP    = 32512

class TrayIcon:
    def __init__(self, tooltip, icon_image=None, menu=None,
                 on_click=None, on_dblclick=None):
        self._tooltip   = tooltip[:63]
        self._icon_img  = icon_image
        self._menu_def  = menu or []
        self._on_click  = on_click
        self._on_dbl    = on_dblclick
        self._hwnd      = None
        self._hicon     = None
        self._alive     = True
        self._click_pending = False
        self._click_timer   = None
        self._dbl_time  = win32gui.GetDoubleClickTime() / 1000.0 + 0.05

    def run(self):
        # Register window class with message map (pywin32 style)
        msg_map = {
            WM_TRAY: self._on_tray_msg,
            win32con.WM_COMMAND: self._on_command_msg,
            win32con.WM_DESTROY: self._on_destroy_msg,
        }

        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = msg_map
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = f"TrayClick_{id(self)}"
        class_atom = win32gui.RegisterClass(wc)

        # Create hidden message window
        self._hwnd = win32gui.CreateWindow(
            class_atom, "TrayClick", 0,
            0, 0, 0, 0, 0, 0, wc.hInstance, None)

        # Load icon
        self._hicon = self._make_hicon()

        # Add tray icon
        flags = win32gui.NIF_ICON | win32gui.NIF_TIP | win32gui.NIF_MESSAGE
        nid = (self._hwnd, 1, flags, WM_TRAY, self._hicon, self._tooltip)
        result = win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)

        # Blocking message loop (proper Win32)
        win32gui.PumpMessages()

        # Cleanup
        try: win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self._hwnd, 1))
        except: pass

    def stop(self):
        self._alive = False
        try: win32gui.PostMessage(self._hwnd, win32con.WM_QUIT, 0, 0)
        except: pass

    def _make_hicon(self):
        if self._icon_img:
            tmp = Path(tempfile.gettempdir()) / f"trayclick_{id(self)}.ico"
            img = self._icon_img.resize((32, 32))
            img.save(str(tmp), format="ICO")
            return win32gui.LoadImage(
                0, str(tmp), win32con.IMAGE_ICON,
                32, 32, win32con.LR_LOADFROMFILE)
        return win32gui.LoadIcon(0, IDI_APP)

    # ── Message handlers (dict-mapped by pywin32) ──────────────────────
    def _on_tray_msg(self, hwnd, msg, wparam, lparam):
        if lparam == win32con.WM_LBUTTONUP:
            if self._click_pending:
                self._click_pending = False
                if self._click_timer:
                    self._click_timer.cancel()
                    self._click_timer = None
                if self._on_dbl:
                    self._on_dbl()
            else:
                self._click_pending = True
                self._click_timer = threading.Timer(
                    self._dbl_time, self._fire_single)
                self._click_timer.start()

        elif lparam == win32con.WM_LBUTTONDBLCLK:
            self._click_pending = False
            if self._click_timer:
                self._click_timer.cancel()
                self._click_timer = None
            if self._on_dbl:
                self._on_dbl()

        elif lparam == win32con.WM_RBUTTONUP:
            self._show_menu()
        return 0

    def _on_command_msg(self, hwnd, msg, wparam, lparam):
        menu_id = win32api.LOWORD(wparam)
        self._fire_menu(menu_id)
        return 0

    def _on_destroy_msg(self, hwnd, msg, wparam, lparam):
        win32gui.PostQuitMessage(0)
        return 0

    def _fire_single(self):
        self._click_pending = False
        self._click_timer = None
        if self._on_click:
            self._on_click()

    def _show_menu(self):
        hmenu = win32gui.CreatePopupMenu()
        real_items = []
        cmd_id = 1000
        for item in self._menu_def:
            if item is None:
                win32gui.AppendMenu(hmenu, win32con.MF_SEPARATOR, 0, "")
            else:
                label, callback = item
                win32gui.AppendMenu(hmenu, win32con.MF_STRING, cmd_id, label)
                real_items.append((cmd_id, callback))
                cmd_id += 1

        self._menu_map = {cid: cb for cid, cb in real_items}

        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self._hwnd)
        win32gui.TrackPopupMenu(
            hmenu, win32con.TPM_LEFTBUTTON,
            pos[0], pos[1], 0, self._hwnd, None)
        win32gui.PostMessage(self._hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(hmenu)

    def _fire_menu(self, cmd_id):
        cb = getattr(self, '_menu_map', {}).get(cmd_id)
        if cb:
            threading.Thread(target=cb, daemon=True).start()
