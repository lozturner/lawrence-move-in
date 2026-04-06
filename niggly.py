"""Niggly Machine v2.0.0 — Focus Rules. IFTTT: focus THIS -> hide THOSE."""
__version__ = "2.0.0"

import json, os, threading, time, tkinter as tk
from tkinter import ttk
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont
import win32gui, win32con, win32process, win32api

CONFIG_PATH = Path(__file__).parent / "niggly_config.json"
POLL_MS = 150

# Catppuccin Mocha
C = dict(
    bg="#1e1e2e", surface="#282840", card="#313244", card_hi="#3b3b55",
    border="#45475a", text="#cdd6f4", dim="#7f849c", blue="#89b4fa",
    green="#a6e3a1", red="#f38ba8", peach="#fab387", mauve="#cba6f7",
    teal="#94e2d5", yellow="#f9e2af", white="#ffffff",
)

FRIENDLY_NAMES = {
    "chrome.exe": ("Chrome", "Browser"), "msedge.exe": ("Edge", "Browser"),
    "firefox.exe": ("Firefox", "Browser"), "explorer.exe": ("File Explorer", "Files"),
    "Code.exe": ("VS Code", "Editor"), "code.exe": ("VS Code", "Editor"),
    "devenv.exe": ("Visual Studio", "IDE"),
    "WindowsTerminal.exe": ("Terminal", "Shell"), "cmd.exe": ("CMD", "Shell"),
    "powershell.exe": ("PowerShell", "Shell"), "pwsh.exe": ("PowerShell", "Shell"),
    "WINWORD.EXE": ("Word", "Office"), "EXCEL.EXE": ("Excel", "Office"),
    "POWERPNT.EXE": ("PowerPoint", "Office"), "OUTLOOK.EXE": ("Outlook", "Email"),
    "Teams.exe": ("Teams", "Chat"), "ms-teams.exe": ("Teams", "Chat"),
    "slack.exe": ("Slack", "Chat"), "Slack.exe": ("Slack", "Chat"),
    "Discord.exe": ("Discord", "Chat"), "discord.exe": ("Discord", "Chat"),
    "Spotify.exe": ("Spotify", "Music"), "spotify.exe": ("Spotify", "Music"),
    "notepad.exe": ("Notepad", "Text"), "Notepad.exe": ("Notepad", "Text"),
    "mstsc.exe": ("Remote Desktop", "Remote"), "Taskmgr.exe": ("Task Manager", "System"),
    "python.exe": ("Python", "Dev"), "pythonw.exe": ("Python", "Dev"),
    "node.exe": ("Node.js", "Dev"), "Figma.exe": ("Figma", "Design"),
    "Obsidian.exe": ("Obsidian", "Notes"), "Notion.exe": ("Notion", "Notes"),
    "claude.exe": ("Claude", "AI"), "ShadowPC.exe": ("Shadow PC", "Remote"),
    "osk.exe": ("On-Screen Keyboard", "System"),
}

SKIP_TITLES = {"Program Manager", "Windows Input Experience"}

def friendly_name(exe, title=""):
    if exe in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[exe]
    clean = exe.replace(".exe", "").replace("_", " ").title()
    return clean, "App"

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"rules": {}, "enabled": True}

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def get_visible_windows():
    results = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or title in SKIP_TITLES:
            return
        r = win32gui.GetWindowRect(hwnd)
        if (r[2] - r[0]) < 50 or (r[3] - r[1]) < 50:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            h = win32api.OpenProcess(0x0410, False, pid)
            exe = os.path.basename(win32process.GetModuleFileNameEx(h, 0))
            win32api.CloseHandle(h)
        except Exception:
            exe = "unknown"
        results.append((hwnd, title, exe))
    win32gui.EnumWindows(cb, None)
    return results

def wkey(title, exe):
    return f"{exe}|{title[:60]}"

def create_icon_image(enabled):
    sz = 64
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = (166, 227, 161) if enabled else (243, 139, 168)
    d.rounded_rectangle([2, 2, sz - 2, sz - 2], radius=12, fill=bg)
    try:
        fnt = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        fnt = ImageFont.load_default()
    d.text((sz // 2, sz // 2), "NM", fill=(30, 30, 46), font=fnt, anchor="mm")
    return img

# ── Focus Monitor ───────────────────────────────────────────

class FocusMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._config_lock = threading.Lock()
        self.config = load_config()
        self.running = True
        self.enabled = self.config.get("enabled", True)
        self._last_fg = None
        self.tray_icon = None

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self.running:
            time.sleep(POLL_MS / 1000)
            with self._lock:
                if not self.enabled:
                    continue
            try:
                fg = win32gui.GetForegroundWindow()
                if fg == self._last_fg:
                    continue
                self._last_fg = fg
                title = win32gui.GetWindowText(fg)
                if not title:
                    continue
                try:
                    _, pid = win32process.GetWindowThreadProcessId(fg)
                    h = win32api.OpenProcess(0x0410, False, pid)
                    exe = os.path.basename(win32process.GetModuleFileNameEx(h, 0))
                    win32api.CloseHandle(h)
                except Exception:
                    continue
                key = wkey(title, exe)
                with self._config_lock:
                    rules = dict(self.config.get("rules", {}))
                hide = set()
                for rk, targets in rules.items():
                    if rk.split("|")[0] == exe or rk == key:
                        hide.update(targets)
                if not hide:
                    continue
                for whwnd, wt, we in get_visible_windows():
                    if whwnd == fg:
                        continue
                    wk = wkey(wt, we)
                    if wk in hide or we in {h.split("|")[0] for h in hide}:
                        try:
                            win32gui.ShowWindow(whwnd, win32con.SW_MINIMIZE)
                        except Exception:
                            pass
            except Exception:
                pass

    def toggle(self):
        with self._lock:
            self.enabled = not self.enabled
        with self._config_lock:
            self.config["enabled"] = self.enabled
            save_config(self.config)
        if self.tray_icon:
            self.tray_icon.icon = create_icon_image(self.enabled)
    def reload_config(self):
        with self._config_lock:
            self.config = load_config()
        with self._lock:
            self.enabled = self.config.get("enabled", True)

# ── Config Window ───────────────────────────────────────────

class ConfigWindow:
    def __init__(self, monitor: FocusMonitor):
        self.mon = monitor
        self._show_lock = threading.Lock()
        self.root = None
        self.rules = []
        self._flash_id = None

    def _load_rules(self):
        self.rules = []
        with self.mon._config_lock:
            for trig, targets in self.mon.config.get("rules", {}).items():
                self.rules.append({"trigger": trig, "hide": list(targets)})

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
        self.root.title(f"Niggly Machine v{__version__}")
        self.root.configure(bg=C["bg"])
        self.root.geometry("1000x700")
        self.root.minsize(800, 500)
        self._load_rules()
        self._build()
        self.root.mainloop()

    def _wmap(self):
        seen = {}
        for _, title, exe in get_visible_windows():
            k = wkey(title, exe)
            if k not in seen and "Niggly Machine" not in title:
                seen[k] = (friendly_name(exe, title), exe, title)
        return seen

    def _key_display(self, k, wmap):
        if not k:
            return "(select a window)"
        if k in wmap:
            (fn, cat), exe, title = wmap[k]
            return f"{fn} ({cat}) -- {title[:40]}"
        parts = k.split("|", 1)
        fn, cat = friendly_name(parts[0], parts[1] if len(parts) > 1 else "")
        return f"{fn} ({cat}) -- {parts[1][:40] if len(parts) > 1 else ''}"

    def _display_to_key(self, disp, wmap):
        for k, ((fn, cat), exe, title) in wmap.items():
            if f"{fn} ({cat}) -- {title[:40]}" == disp:
                return k
        return ""

    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg=C["surface"], height=52)
        hdr.pack(fill="x"); hdr.pack_propagate(False)

        left = tk.Frame(hdr, bg=C["surface"])
        left.pack(side="left", padx=16, pady=8)
        badge = tk.Label(left, text=" NM ", font=("Segoe UI", 9, "bold"),
                         fg=C["bg"], bg=C["mauve"])
        badge.pack(side="left", padx=(0, 10))
        tk.Label(left, text=f"Niggly Machine v{__version__}",
                 font=("Segoe UI", 15, "bold"), fg=C["text"],
                 bg=C["surface"]).pack(side="left")

        self._status_frame = tk.Frame(hdr, bg=C["surface"])
        self._status_frame.pack(side="right", padx=16, pady=8)
        self._draw_status()

        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x")

        # Toolbar
        tb = tk.Frame(self.root, bg=C["bg"])
        tb.pack(fill="x", padx=20, pady=(14, 10))
        self._pill(tb, "+ New Rule", C["green"], self._add_rule).pack(side="left", padx=(0, 8))
        self._pill(tb, "Refresh", C["blue"], self._refresh).pack(side="left", padx=(0, 8))
        self._pill(tb, "Save All", C["peach"], self._save).pack(side="left", padx=(0, 8))
        self._pause_btn = self._pill(
            tb, "Pause" if self.mon.enabled else "Resume",
            C["yellow"] if self.mon.enabled else C["green"], self._toggle)
        self._pause_btn.pack(side="right")

        # Scrollable area
        wrap = tk.Frame(self.root, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.canvas = tk.Canvas(wrap, bg=C["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.cards = tk.Frame(self.canvas, bg=C["bg"])
        self._cw = self.canvas.create_window((0, 0), window=self.cards, anchor="nw")
        self.cards.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self._cw, width=e.width))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-(e.delta // 120), "units"))
        self._refresh()
    def _pill(self, parent, text, color, cmd):
        btn = tk.Label(parent, text=f"  {text}  ", font=("Segoe UI", 10, "bold"),
                       fg=color, bg=C["card"], cursor="hand2", padx=8, pady=4)
        btn.bind("<Button-1>", lambda e: cmd())
        btn.bind("<Enter>", lambda e: btn.configure(bg=C["card_hi"]))
        btn.bind("<Leave>", lambda e: btn.configure(bg=C["card"]))
        btn._color = color
        return btn

    def _draw_status(self):
        for w in self._status_frame.winfo_children():
            w.destroy()
        if self.mon.enabled:
            col, txt = C["green"], "  ACTIVE  "
        else:
            col, txt = C["red"], "  PAUSED  "
        lbl = tk.Label(self._status_frame, text=txt, font=("Segoe UI", 9, "bold"),
                       fg=col, bg=C["card"])
        lbl.pack()

    # ── Cards ──

    def _refresh(self):
        for w in self.cards.winfo_children():
            w.destroy()
        if not self.rules:
            self._empty_state()
            return
        for i, rule in enumerate(self.rules):
            self._card(i, rule)

    def _empty_state(self):
        f = tk.Frame(self.cards, bg=C["bg"])
        f.pack(fill="both", expand=True, pady=80)
        tk.Label(f, text="No rules yet", font=("Segoe UI", 18, "bold"),
                 fg=C["dim"], bg=C["bg"]).pack()
        tk.Label(f, text="Click  + New Rule  to get started",
                 font=("Segoe UI", 11), fg=C["border"], bg=C["bg"]).pack(pady=(6, 0))

    def _card(self, idx, rule):
        wmap = self._wmap()
        # Outer: coloured left border
        outer = tk.Frame(self.cards, bg=C["mauve"])
        outer.pack(fill="x", pady=(0, 12))
        card = tk.Frame(outer, bg=C["card"])
        card.pack(fill="both", expand=True, padx=(4, 0))

        # Delete button
        top = tk.Frame(card, bg=C["card"])
        top.pack(fill="x")
        x_btn = tk.Label(top, text=" \u2715 ", font=("Segoe UI", 11),
                         fg=C["dim"], bg=C["card"], cursor="hand2")
        x_btn.pack(side="right", padx=(0, 4), pady=(4, 0))
        x_btn.bind("<Button-1>", lambda e, i=idx: self._del_rule(i))
        x_btn.bind("<Enter>", lambda e: x_btn.configure(fg=C["red"]))
        x_btn.bind("<Leave>", lambda e: x_btn.configure(fg=C["dim"]))

        # IF section
        if_row = tk.Frame(card, bg=C["card"])
        if_row.pack(fill="x", padx=16, pady=(4, 0))
        tk.Label(if_row, text="IF", font=("Segoe UI", 12, "bold"),
                 fg=C["mauve"], bg=C["card"]).pack(side="left", padx=(0, 8))
        tk.Label(if_row, text="I focus", font=("Segoe UI", 10),
                 fg=C["dim"], bg=C["card"]).pack(side="left")

        trig_frame = tk.Frame(card, bg=C["card"])
        trig_frame.pack(fill="x", padx=16, pady=(6, 8))
        trig_disp = self._key_display(rule["trigger"], wmap)
        trig_var = tk.StringVar(value=trig_disp)
        opts = sorted({self._key_display(k, wmap) for k in wmap})
        if trig_disp not in opts:
            opts.append(trig_disp); opts.sort()
        combo = ttk.Combobox(trig_frame, textvariable=trig_var, values=opts,
                             state="readonly", font=("Segoe UI", 11), width=50)
        combo.pack(side="left", fill="x", expand=True)
        combo.bind("<<ComboboxSelected>>",
                   lambda e, i=idx, v=trig_var: self._on_trigger(i, v.get(), wmap))

        # Arrow
        tk.Label(card, text="\u25bc", font=("Segoe UI", 14),
                 fg=C["border"], bg=C["card"]).pack(anchor="w", padx=30)

        # THEN section
        then_row = tk.Frame(card, bg=C["card"])
        then_row.pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(then_row, text="THEN", font=("Segoe UI", 12, "bold"),
                 fg=C["peach"], bg=C["card"]).pack(side="left", padx=(0, 8))
        tk.Label(then_row, text="hide these", font=("Segoe UI", 10),
                 fg=C["dim"], bg=C["card"]).pack(side="left")

        tk.Frame(card, bg=C["border"], height=1).pack(fill="x", padx=16, pady=(4, 8))

        # Chips
        chips = tk.Frame(card, bg=C["card"])
        chips.pack(fill="x", padx=16, pady=(0, 14))
        row = tk.Frame(chips, bg=C["card"]); row.pack(fill="x", pady=2)
        n = 0
        hide_set = set(rule.get("hide", []))
        for k, ((fn, cat), exe, title) in sorted(wmap.items(), key=lambda x: x[1][0][0].lower()):
            if k == rule["trigger"]:
                continue
            active = k in hide_set
            self._chip(row, fn, cat, active, idx, k).pack(side="left", padx=(0, 6), pady=3)
            n += 1
            if n % 5 == 0:
                row = tk.Frame(chips, bg=C["card"]); row.pack(fill="x", pady=2)

    def _chip(self, parent, name, cat, active, ridx, wk):
        txt = f"\u2715 {name}  {cat}" if active else f"{name}  {cat}"
        fg = C["white"] if active else C["dim"]
        bg = C["red"] if active else C["card"]
        bg_hi = "#e06080" if active else C["card_hi"]
        lbl = tk.Label(parent, text=f" {txt} ", font=("Segoe UI", 9),
                       fg=fg, bg=bg, cursor="hand2", padx=4, pady=2)
        if not active:
            lbl.configure(highlightbackground=C["border"], highlightthickness=1)
        lbl.bind("<Button-1>", lambda e: self._toggle_chip(ridx, wk))
        lbl.bind("<Enter>", lambda e: lbl.configure(bg=bg_hi))
        lbl.bind("<Leave>", lambda e: lbl.configure(bg=bg))
        return lbl

    # ── Actions ──

    def _toggle_chip(self, ridx, wk):
        hide = self.rules[ridx].get("hide", [])
        if wk in hide:
            hide.remove(wk)
        else:
            hide.append(wk)
        self.rules[ridx]["hide"] = hide
        self._refresh()

    def _on_trigger(self, ridx, disp, wmap):
        k = self._display_to_key(disp, wmap)
        self.rules[ridx]["trigger"] = k
        hide = self.rules[ridx].get("hide", [])
        if k in hide:
            hide.remove(k)
        self._refresh()

    def _add_rule(self):
        self.rules.append({"trigger": "", "hide": []})
        self._refresh()
        self.root.after(100, lambda: self.canvas.yview_moveto(1.0))

    def _del_rule(self, idx):
        if 0 <= idx < len(self.rules):
            self.rules.pop(idx)
            self._refresh()

    def _save(self):
        rules = {}
        for r in self.rules:
            if r["trigger"] and r.get("hide"):
                rules[r["trigger"]] = r["hide"]
        with self.mon._config_lock:
            self.mon.config["rules"] = rules
            save_config(self.mon.config)
        self.mon.reload_config()
        self._flash_saved()

    def _flash_saved(self):
        if self._flash_id:
            try:
                self.root.after_cancel(self._flash_id)
            except Exception:
                pass
        lbl = tk.Label(self.root, text="  Saved!  ", font=("Segoe UI", 12, "bold"),
                       fg=C["bg"], bg=C["green"], padx=20, pady=8)
        lbl.place(relx=0.5, rely=0.5, anchor="center")
        def _kill():
            try:
                if self.root and self.root.winfo_exists() and lbl.winfo_exists():
                    lbl.destroy()
            except Exception:
                pass
            self._flash_id = None
        self._flash_id = self.root.after(1200, _kill)

    def _toggle(self):
        self.mon.toggle()
        self._draw_status()
        txt = "Pause" if self.mon.enabled else "Resume"
        col = C["yellow"] if self.mon.enabled else C["green"]
        self._pause_btn.configure(text=f"  {txt}  ", fg=col)


# ── Main ───────────────────────────────────────────────────────

def main():
    mon = FocusMonitor()
    ui = ConfigWindow(mon)

    def open_cfg(icon, item):
        threading.Thread(target=ui.show, daemon=True).start()

    def toggle(icon, item):
        mon.toggle()
        icon.icon = create_icon_image(mon.enabled)

    def quit_app(icon, item):
        mon.running = False
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Configure Rules", open_cfg, default=True),
        pystray.MenuItem("Toggle On/Off", toggle),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Niggly Machine", quit_app),
    )
    icon = pystray.Icon("niggly_machine", create_icon_image(mon.enabled),
                        f"Focus Rules v{__version__}", menu)
    mon.tray_icon = icon
    mon.start()

    if not CONFIG_PATH.exists():
        save_config(mon.config)
    threading.Timer(0.5, lambda: threading.Thread(target=ui.show, daemon=True).start()).start()
    icon.run()


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("niggly.py")
    main()
