"""
Lawrence: Move In — Nag v1.0.0
Timetable nagger. Pops up every 5 minutes reminding you what you should be doing.
Reads from nag_timetable.json. Links to your Google Sheet. Click to open/switch.

Columns from your spreadsheet:
  Time, Priority, Category, What To Do, Details, Duration, Prep Before,
  Prep Time, Follow Up, Follow Time, Done?, Notes
"""
__version__ = "1.0.0"

import json, os, subprocess, sys, threading, time, tkinter as tk, webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "nag_timetable.json"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1rc0_hbzOUnfvEfZtD4tPgHxaCxR4hsSxl1F4Y1l94EM/edit?gid=1535495397#gid=1535495397"

BG="#0a0a14";BG2="#12122a";CARD="#1a1a3a";CARD_HI="#252545"
TEXT="#cdd6f4";DIM="#5a5a80";LAV="#b4befe";GRN="#a6e3a1"
PCH="#fab387";MAU="#cba6f7";RED="#f38ba8";YEL="#f9e2af";BLUE="#89b4fa"

# ── Default timetable (from what I can see in the sheet) ──────────────────────
DEFAULT_TIMETABLE = {
    "sheet_url": SHEET_URL,
    "nag_interval_minutes": 5,
    "tasks": [
        {"time":"07:00","priority":"!!","category":"WAKE UP","what":"Get up, bathroom, face wash","details":"Alarm off. Feet on floor. Cold water.","duration":"15m","prep":"Phone charged overnight","after":"Check phone battery","done":False},
        {"time":"07:15","priority":"!","category":"DRESSING","what":"Get dressed","details":"Joggers, t-shirt, socks.","duration":"15m","prep":"Clothes laid out","after":"Dirty clothes basket","done":False},
        {"time":"07:30","priority":"!","category":"BREAKFAST","what":"Breakfast","details":"","duration":"15m","prep":"","after":"","done":False},
        {"time":"07:45","priority":"!","category":"MEDS","what":"Take medication","details":"","duration":"5m","prep":"","after":"","done":False},
        {"time":"08:00","priority":"!!","category":"KIDS","what":"Kids ready","details":"","duration":"30m","prep":"","after":"","done":False},
        {"time":"08:30","priority":"!!","category":"SCHOOL RUN","what":"School run","details":"","duration":"30m","prep":"","after":"","done":False},
        {"time":"09:00","priority":"!!","category":"WORK","what":"Start work block","details":"","duration":"60m","prep":"","after":"","done":False},
        {"time":"10:00","priority":"!","category":"BREAK","what":"Break — move, drink water","details":"","duration":"15m","prep":"","after":"","done":False},
        {"time":"10:15","priority":"!!","category":"WORK","what":"Work block 2","details":"","duration":"60m","prep":"","after":"","done":False},
        {"time":"11:15","priority":"!","category":"BREAK","what":"Break","details":"","duration":"15m","prep":"","after":"","done":False},
        {"time":"11:30","priority":"!!","category":"WORK","what":"Work block 3","details":"","duration":"60m","prep":"","after":"","done":False},
        {"time":"12:30","priority":"!","category":"LUNCH","what":"Lunch","details":"","duration":"30m","prep":"","after":"","done":False},
        {"time":"13:00","priority":"!!","category":"WORK","what":"Afternoon work","details":"","duration":"90m","prep":"","after":"","done":False},
        {"time":"14:30","priority":"!","category":"SCHOOL","what":"School pickup","details":"","duration":"30m","prep":"","after":"","done":False},
        {"time":"15:00","priority":"!","category":"KIDS","what":"Kids time / homework","details":"","duration":"60m","prep":"","after":"","done":False},
        {"time":"16:00","priority":"!","category":"WORK","what":"Evening work block","details":"","duration":"60m","prep":"","after":"","done":False},
        {"time":"17:00","priority":"!","category":"DINNER","what":"Cook / dinner","details":"","duration":"45m","prep":"","after":"","done":False},
        {"time":"18:00","priority":"","category":"FAMILY","what":"Family time","details":"","duration":"60m","prep":"","after":"","done":False},
        {"time":"19:00","priority":"","category":"KIDS","what":"Kids bedtime routine","details":"","duration":"60m","prep":"","after":"","done":False},
        {"time":"20:00","priority":"","category":"FREE","what":"Free time / projects","details":"","duration":"120m","prep":"","after":"","done":False},
        {"time":"22:00","priority":"!","category":"WIND DOWN","what":"Wind down, no screens","details":"","duration":"30m","prep":"","after":"","done":False},
        {"time":"22:30","priority":"!!","category":"SLEEP","what":"Bed","details":"","duration":"","prep":"","after":"","done":False},
    ]
}

def load_timetable():
    if CONFIG_PATH.exists():
        try: return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except: pass
    save_timetable(DEFAULT_TIMETABLE)
    return dict(DEFAULT_TIMETABLE)

def save_timetable(t):
    CONFIG_PATH.write_text(json.dumps(t, indent=2, ensure_ascii=False), encoding="utf-8")

def time_to_minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)

def current_task(tasks):
    now = datetime.now()
    now_mins = now.hour * 60 + now.minute
    current = None
    next_task = None
    for i, t in enumerate(tasks):
        t_mins = time_to_minutes(t["time"])
        if t_mins <= now_mins:
            current = t
        elif next_task is None and t_mins > now_mins:
            next_task = t
    return current, next_task

# ── App ───────────────────────────────────────────────────────────────────────
class NagApp:
    def __init__(self):
        self.tt = load_timetable()
        self._alive = True
        self._nag_dlg = None

        self.root = tk.Tk()
        self.root.withdraw()

        self._nag_loop()
        self._start_tray()
        self.root.mainloop()

    def _nag_loop(self):
        if not self._alive: return
        self._show_nag()
        interval = self.tt.get("nag_interval_minutes", 5) * 60 * 1000
        self.root.after(interval, self._nag_loop)

    def _show_nag(self):
        if self._nag_dlg and self._nag_dlg.winfo_exists():
            self._nag_dlg.destroy()

        tasks = self.tt.get("tasks", [])
        cur, nxt = current_task(tasks)
        if not cur:
            return

        now = datetime.now().strftime("%H:%M")

        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.attributes("-alpha", 0.96)
        dlg.configure(bg=BG)
        self._nag_dlg = dlg

        sw = dlg.winfo_screenwidth()
        w, h = 420, 280
        dlg.geometry(f"{w}x{h}+{sw-w-20}+{40}")

        # Header
        pri_col = RED if cur.get("priority","") == "!!" else YEL if cur.get("priority") else DIM
        hdr = tk.Frame(dlg, bg=BG2)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  Hey. It's {now}.", font=("Segoe UI",11,"bold"),
                 fg=LAV, bg=BG2).pack(side="left", padx=6, ipady=6)
        tk.Label(hdr, text=cur.get("priority",""), font=("Segoe UI",12,"bold"),
                 fg=pri_col, bg=BG2).pack(side="left")
        xb = tk.Label(hdr, text=" ✕ ", font=("Consolas",10),
                       fg=DIM, bg=BG2, cursor="hand2")
        xb.pack(side="right", padx=4)
        xb.bind("<Button-1>", lambda _: dlg.destroy())

        # Current task
        tk.Label(dlg, text="You should be doing:",
                 font=("Segoe UI",9), fg=DIM, bg=BG).pack(anchor="w", padx=14, pady=(8,2))

        tf = tk.Frame(dlg, bg=CARD)
        tf.pack(fill="x", padx=12, pady=2)
        tk.Label(tf, text=cur["category"], font=("Consolas",9,"bold"),
                 fg=pri_col, bg=CARD, padx=8).pack(anchor="w", pady=(6,0))
        tk.Label(tf, text=cur["what"], font=("Segoe UI",14,"bold"),
                 fg=TEXT, bg=CARD, padx=8, wraplength=380).pack(anchor="w")
        if cur.get("details"):
            tk.Label(tf, text=cur["details"], font=("Segoe UI",9),
                     fg=DIM, bg=CARD, padx=8, wraplength=380).pack(anchor="w")
        if cur.get("duration"):
            tk.Label(tf, text=f"Duration: {cur['duration']}", font=("Segoe UI",8),
                     fg=DIM, bg=CARD, padx=8).pack(anchor="w", pady=(0,6))

        # Done checkbox
        done_var = tk.BooleanVar(value=cur.get("done", False))
        def _toggle_done():
            cur["done"] = done_var.get()
            save_timetable(self.tt)

        db = tk.Checkbutton(dlg, text=" Done — tick this off", variable=done_var,
                            command=_toggle_done, bg=BG, fg=GRN,
                            activebackground=BG, selectcolor=BG,
                            font=("Segoe UI",9))
        db.pack(anchor="w", padx=14, pady=4)

        # Next up
        if nxt:
            tk.Label(dlg, text=f"Next: {nxt['time']} — {nxt['category']}: {nxt['what']}",
                     font=("Segoe UI",8), fg=DIM, bg=BG, padx=14).pack(anchor="w")

        # Buttons
        bf = tk.Frame(dlg, bg=BG)
        bf.pack(fill="x", padx=12, pady=(6,8))

        for txt, col, fn in [
            ("📋 Open Sheet", BLUE, lambda: webbrowser.open(self.tt.get("sheet_url", SHEET_URL))),
            ("📋 Copy task", LAV, lambda: self._copy_task(cur)),
            ("⏭ Skip to next", DIM, lambda: dlg.destroy()),
            ("✕ Dismiss", DIM, lambda: dlg.destroy()),
        ]:
            b = tk.Label(bf, text=txt, font=("Segoe UI",8),
                         fg=col, bg=CARD, padx=6, pady=3, cursor="hand2")
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, f=fn: f())
            b.bind("<Enter>", lambda e, w=b: w.config(bg=CARD_HI))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=CARD))

        # Auto-dismiss after 2 minutes
        dlg.after(120000, lambda: dlg.destroy() if dlg.winfo_exists() else None)

    def _copy_task(self, task):
        text = f"[{task['time']}] {task['category']}: {task['what']}"
        if task.get("details"): text += f"\n{task['details']}"
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _open_full(self):
        """Open full timetable view."""
        tasks = self.tt.get("tasks", [])
        now_mins = datetime.now().hour * 60 + datetime.now().minute

        dlg = tk.Toplevel(self.root)
        dlg.title("Today's Timetable")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=BG)
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        dlg.geometry(f"450x500+{(sw-450)//2}+{(sh-500)//2}")

        tk.Label(dlg, text=f"  Monday 6 April — Timetable", bg=BG2, fg=LAV,
                 font=("Consolas",11,"bold"), anchor="w").pack(fill="x", ipady=8)

        cf = tk.Frame(dlg, bg=BG)
        cf.pack(fill="both", expand=True, padx=8, pady=4)

        cv = tk.Canvas(cf, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(cf, orient="vertical", command=cv.yview, width=5)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(fill="both", expand=True)
        inner = tk.Frame(cv, bg=BG)
        cw = cv.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.config(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(cw, width=e.width))

        for t in tasks:
            t_mins = time_to_minutes(t["time"])
            is_current = (t_mins <= now_mins and
                          (t == tasks[-1] or time_to_minutes(tasks[tasks.index(t)+1]["time"]) > now_mins))
            is_done = t.get("done", False)
            is_past = t_mins < now_mins and not is_current

            bg_c = "#1a2a1a" if is_current else ("#1a1a2a" if is_done else CARD)
            fg_c = GRN if is_current else (DIM if is_done else TEXT)
            pri_c = RED if t.get("priority") == "!!" else YEL if t.get("priority") else DIM

            f = tk.Frame(inner, bg=bg_c, pady=3)
            f.pack(fill="x", pady=1)

            tk.Label(f, text=t["time"], font=("Consolas",9,"bold"),
                     fg=pri_c, bg=bg_c, width=5).pack(side="left", padx=4)
            tk.Label(f, text=t["category"], font=("Consolas",7,"bold"),
                     fg=pri_c, bg=bg_c, width=10, anchor="w").pack(side="left")
            tk.Label(f, text=("✓ " if is_done else "► " if is_current else "  ") + t["what"],
                     font=("Segoe UI",9), fg=fg_c, bg=bg_c,
                     anchor="w").pack(side="left", fill="x", expand=True)

        # Scroll to current task area
        dlg.update_idletasks()
        # Find approximate position
        cur_idx = 0
        for i, t in enumerate(tasks):
            if time_to_minutes(t["time"]) <= now_mins:
                cur_idx = i
        if len(tasks) > 0:
            frac = max(0, (cur_idx - 2) / len(tasks))
            cv.yview_moveto(frac)

        bf = tk.Frame(dlg, bg=BG2)
        bf.pack(fill="x")
        for txt, fn in [
            ("📋 Open Sheet", lambda: webbrowser.open(self.tt.get("sheet_url", SHEET_URL))),
            ("Close", lambda: dlg.destroy()),
        ]:
            b = tk.Label(bf, text=f" {txt} ", font=("Segoe UI",8),
                         fg=TEXT, bg=CARD, padx=6, pady=4, cursor="hand2")
            b.pack(side="left", padx=4, pady=4)
            b.bind("<Button-1>", lambda e, f=fn: f())

    def _start_tray(self):
        img = Image.new("RGBA",(64,64),(0,0,0,0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([4,4,59,59], radius=12, fill=(249,226,175))
        try: fnt = ImageFont.truetype("consola.ttf",20)
        except: fnt = ImageFont.load_default()
        bb = d.textbbox((0,0),"NG",font=fnt)
        d.text(((64-(bb[2]-bb[0]))//2,(64-(bb[3]-bb[1]))//2),
               "NG", fill="#0a0a14", font=fnt)

        def _nag_now(icon, item):
            self.root.after(0, self._show_nag)
        def _full(icon, item):
            self.root.after(0, self._open_full)
        def _sheet(icon, item):
            webbrowser.open(self.tt.get("sheet_url", SHEET_URL))
        def _interval_lbl(_):
            return f"Nag every {self.tt.get('nag_interval_minutes',5)} min"
        def _cycle(icon, item):
            opts = [1,2,3,5,10,15,30]
            cur = self.tt.get("nag_interval_minutes",5)
            try: idx = opts.index(cur)
            except: idx = 0
            self.tt["nag_interval_minutes"] = opts[(idx+1)%len(opts)]
            save_timetable(self.tt)
        def _quit(icon, item):
            self._alive = False
            icon.stop()
            self.root.destroy()

        menu = pystray.Menu(
            pystray.MenuItem("Nag me now", _nag_now),
            pystray.MenuItem("Full timetable", _full),
            pystray.MenuItem("Open Google Sheet", _sheet),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_interval_lbl, _cycle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", _quit),
        )
        self._tray = pystray.Icon("nag", img, "Nag", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()


if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("nag.py")
    NagApp()
