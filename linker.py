"""
Lawrence: Move In — Linker v2.1.0
  • Resize grip  ◢
  • Zoom  +/−  (tiles, icons, text all scale)
  • Emoji icons  — per-phrase, shown large on tile
  • Image icons  — per-phrase image file, shown on tile
  • ⭐ Pinned / Favourites
  • Instant-add bar
  • ✨ AI auto-suggest (screenshot → Claude)
  • ⟳ Restart in right-click menu
"""
__version__ = "2.2.0"

import base64, io, json, os, subprocess, sys, threading, time, tkinter as tk
from pathlib import Path

import mss
import pystray
from PIL import Image, ImageDraw, ImageFont, ImageTk

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "linker_config.json"
API_CFG     = SCRIPT_DIR / "kidlin_config.json"
PYTHONW     = Path(sys.executable).with_name("pythonw.exe")

# ── Palette ──────────────────────────────────────────────────────────────────
BG      = "#0a0a14"
BG2     = "#12122a"
CARD    = "#1a1a3a"
CARD_HI = "#252545"
BORDER  = "#2a2a50"
TEXT    = "#cdd6f4"
DIM     = "#5a5a80"
LAVENDER= "#b4befe"
BLUE    = "#89b4fa"
GREEN   = "#a6e3a1"
PEACH   = "#fab387"
MAUVE   = "#cba6f7"
RED     = "#f38ba8"
TEAL    = "#94e2d5"
YELLOW  = "#f9e2af"
PINK    = "#f5c2e7"
SKY     = "#89dceb"

# ── Phrase data model ─────────────────────────────────────────────────────────
# Each phrase is {"text": str, "emoji": str, "image": str|null}
# Backward-compat: plain strings are migrated on load.

def _p(text, emoji="", image=None):
    return {"text": text, "emoji": emoji, "image": image}

PINNED_CAT = {"name":"Pinned","color":YELLOW,"phrases":[],"_pinned_bucket":True}

DEFAULT_CATEGORIES = [
    {"name":"Transition","color":BLUE,"phrases":[
        _p("and then","➡️"),_p("so then","🔜"),_p("which leads to","🔗"),
        _p("that means","💡"),_p("which means","💡"),_p("so from there","📍"),
        _p("at which point","📌"),_p("and from that","🔄"),
        _p("moving on to","⏩"),_p("stepping into","👣")]},
    {"name":"Recall","color":MAUVE,"phrases":[
        _p("that reminds me","🔔"),_p("going back to","↩️"),
        _p("speaking of which","💬"),_p("on that note","🎵"),
        _p("related to that","🔗"),_p("circling back","🔁"),
        _p("which makes me think of","🤔"),_p("that connects to","🔌"),
        _p("bringing it back","📎"),_p("on the subject of","📚")]},
    {"name":"Clarify","color":TEAL,"phrases":[
        _p("what I mean is","🗣️"),_p("the thing is","⚡"),
        _p("basically","📝"),_p("to put it another way","🔄"),
        _p("more specifically","🔍"),_p("what I'm saying is","💬"),
        _p("to be clear","✅"),_p("let me rephrase","✏️"),
        _p("what that looks like is","👁️"),_p("the actual thing is","🎯")]},
    {"name":"Continue","color":GREEN,"phrases":[
        _p("also","➕"),_p("and another thing","📌"),_p("not only that","⬆️"),
        _p("on top of that","🏔️"),_p("and as well","➕"),_p("plus","➕"),
        _p("additionally","📎"),_p("and the other one","2️⃣"),
        _p("place the other","📋"),_p("there's also","👉")]},
    {"name":"Conclude","color":YELLOW,"phrases":[
        _p("so basically","🏁"),_p("the point is","🎯"),_p("bottom line","📊"),
        _p("the key thing is","🔑"),_p("what it comes down to","⚖️"),
        _p("in short","📏"),_p("the takeaway is","📦"),_p("ultimately","🏆"),
        _p("what matters here is","❗"),_p("to sum it up","📋")]},
    {"name":"Contrast","color":PEACH,"phrases":[
        _p("but then","⚡"),_p("on the other hand","🤲"),_p("that said","🔄"),
        _p("although","🌗"),_p("however","↔️"),_p("whereas","⚖️"),
        _p("at the same time","⏱️"),_p("even so","🤷"),
        _p("despite that","💪"),_p("the flip side is","🪙")]},
    {"name":"Example","color":PINK,"phrases":[
        _p("for example","📌"),_p("like when","🕐"),_p("so imagine","🎨"),
        _p("to illustrate","🖼️"),_p("take the case of","📁"),
        _p("a classic example","📖"),_p("picture this","🖼️"),
        _p("like the time","⏰"),_p("same as","🟰"),_p("similar to","≈")]},
    {"name":"Casual","color":SKY,"phrases":[
        _p("oh and","😮"),_p("anyway","🤷"),_p("right so","👉"),
        _p("yeah and","😄"),_p("so yeah","😊"),_p("obviously","🙄"),
        _p("naturally","🌿"),_p("which, you know","😏"),
        _p("it's like","🤔"),_p("kind of like","🌊")]},
]

# ── Migration ─────────────────────────────────────────────────────────────────
def _migrate_phrases(phrases):
    result = []
    for p in phrases:
        if isinstance(p, str):
            result.append(_p(p))
        elif isinstance(p, dict) and "text" in p:
            p.setdefault("emoji", "")
            p.setdefault("image", None)
            result.append(p)
    return result

# ── Config ────────────────────────────────────────────────────────────────────
def load_config():
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            names = [c["name"] for c in cfg.get("categories",[])]
            if "Pinned" not in names:
                cfg.setdefault("categories",[]).insert(0,dict(PINNED_CAT))
            for cat in cfg["categories"]:
                if cat["name"] == "Pinned":
                    cat["_pinned_bucket"] = True
                cat["phrases"] = _migrate_phrases(cat["phrases"])
            cfg.setdefault("zoom", 1.0)
            return cfg
        except Exception:
            pass
    cats = [dict(PINNED_CAT)] + [dict(c) for c in DEFAULT_CATEGORIES]
    cfg = {"categories": cats, "collapsed": [], "pos":[None,None],
           "size":[260,640], "suffix":" ", "zoom":1.0}
    save_config(cfg)
    return cfg

def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False),
                           encoding="utf-8")

def load_api():
    try:
        if API_CFG.exists():
            d = json.loads(API_CFG.read_text())
            return d.get("api_key",""), d.get("model","claude-sonnet-4-20250514")
    except Exception:
        pass
    return "", "claude-sonnet-4-20250514"

# ── Helpers ───────────────────────────────────────────────────────────────────
def copy_clip(root, text):
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()

def abbrev(text):
    words = text.split()
    if len(words) == 1:
        return text[:2].upper()
    return (words[0][0] + words[-1][0]).upper()

def hex_rgb(h):
    return int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)

def make_letter_tile(ab, color, size):
    size = max(20, size)
    img = Image.new("RGBA",(size,size),(0,0,0,0))
    d   = ImageDraw.Draw(img)
    r,g,b = hex_rgb(color)
    d.rounded_rectangle([0,0,size-1,size-1], radius=max(4,size//6),
                        fill=(r,g,b,210))
    fs = max(9, int(size * 0.28))
    try:    fnt = ImageFont.truetype("consola.ttf", fs)
    except: fnt = ImageFont.load_default()
    bb = d.textbbox((0,0), ab, font=fnt)
    d.text(((size-(bb[2]-bb[0]))//2,(size-(bb[3]-bb[1]))//2),
           ab, fill="#0a0a14", font=fnt)
    return img

def make_image_tile(image_path, size):
    """Load user image, square-crop, rounded corners."""
    try:
        img = Image.open(image_path).convert("RGBA")
        s   = min(img.size)
        left = (img.width - s) // 2
        top  = (img.height - s) // 2
        img  = img.crop((left, top, left+s, top+s))
        img  = img.resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size,size), 0)
        md   = ImageDraw.Draw(mask)
        md.rounded_rectangle([0,0,size-1,size-1], radius=max(4,size//6), fill=255)
        img.putalpha(mask)
        return img
    except Exception:
        return None

def make_tray_img():
    img = Image.new("RGBA",(64,64),(0,0,0,0))
    d   = ImageDraw.Draw(img)
    d.rounded_rectangle([4,4,59,59], radius=12, fill=(180,190,254,255))
    try:    fnt = ImageFont.truetype("consola.ttf",22)
    except: fnt = ImageFont.load_default()
    bb = d.textbbox((0,0),"LK",font=fnt)
    d.text(((64-(bb[2]-bb[0]))//2,(64-(bb[3]-bb[1]))//2),
           "LK", fill="#0a0a14", font=fnt)
    return img

def take_screenshot_b64():
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[0])
        img = Image.frombytes("RGB",raw.size,raw.bgra,"raw","BGRX")
    if img.width > 1280:
        img = img.resize((1280,int(img.height*1280/img.width)),Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf,format="JPEG",quality=72)
    return base64.b64encode(buf.getvalue()).decode()

# ── Zoom helpers ──────────────────────────────────────────────────────────────
ZOOM_STEPS = [0.7, 0.85, 1.0, 1.25, 1.5, 1.75, 2.0]

def z(val, zoom):
    return max(1, int(val * zoom))

# ── App ───────────────────────────────────────────────────────────────────────
class LinkerApp:
    def __init__(self):
        self.cfg      = load_config()
        self._photos   = []
        self._flash_id = None
        self._tray     = None
        self._zoom     = float(self.cfg.get("zoom", 1.0))
        self._multi    = False          # multi-select mode
        self._selected = []             # list of selected phrase texts
        self._join     = " "            # how to join: " ", ", ", "\n"

        self.root = tk.Tk()
        self.root.title(f"Linker v{__version__}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)
        self.root.configure(bg=BG)

        w, h   = self.cfg.get("size", [260,640])
        px, py = self.cfg.get("pos",  [None,None])
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        px = px if px is not None else sw - w - 12
        py = py if py is not None else (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{px}+{py}")
        self._w, self._h = w, h

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._render())
        self._ph_active  = False

        self._build()
        self._render()
        self._start_tray()
        self.root.mainloop()

    # ── Build skeleton ────────────────────────────────────────────────────
    def _build(self):
        # Title bar
        self._bar = tk.Frame(self.root, bg=BG2, height=30)
        self._bar.pack(fill="x")
        self._bar.pack_propagate(False)

        tk.Label(self._bar, text=f"  Linker v{__version__}",
                 font=("Segoe UI",9,"bold"), fg=LAVENDER, bg=BG2).pack(side="left")

        for txt, col, cmd in [
            (" ✕ ", RED,    self._quit),
            (" ✨ ", YELLOW, self._ai_suggest),
        ]:
            b = tk.Label(self._bar, text=txt, font=("Segoe UI",9 if txt!=" ✕ " else 10),
                         fg=col, bg=BG2, cursor="hand2", padx=2)
            b.pack(side="right")
            b.bind("<Button-1>", lambda e, fn=cmd: fn())
            b.bind("<Enter>", lambda e, w=b: w.config(bg=CARD))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=BG2))

        self._bar.bind("<Button-1>", self._drag_start)
        self._bar.bind("<B1-Motion>", self._drag_move)
        for child in self._bar.winfo_children():
            child.bind("<Button-1>", self._drag_start)
            child.bind("<B1-Motion>", self._drag_move)

        # Search
        sf = tk.Frame(self.root, bg=BG, pady=3)
        sf.pack(fill="x", padx=6)
        self._search_e = tk.Entry(
            sf, textvariable=self._search_var,
            bg=CARD, fg=TEXT, insertbackground=LAVENDER,
            relief="flat", font=("Segoe UI",9),
            highlightbackground=BORDER, highlightthickness=1)
        self._search_e.pack(fill="x", ipady=4)
        self._set_ph()
        self._search_e.bind("<FocusIn>",  self._ph_in)
        self._search_e.bind("<FocusOut>", self._ph_out)

        # Scroll area
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=2)
        self._canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(container, orient="vertical",
                           command=self._canvas.yview, width=5)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(fill="both", expand=True)
        self._inner = tk.Frame(self._canvas, bg=BG)
        self._cw = self._canvas.create_window((0,0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
            lambda e: self._canvas.config(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._cw, width=e.width))
        self._canvas.bind("<Enter>",
            lambda e: self.root.bind_all("<MouseWheel>", self._wheel))
        self._canvas.bind("<Leave>",
            lambda e: self.root.unbind_all("<MouseWheel>"))
        # Right-click on empty canvas = window menu
        self._canvas.bind("<Button-3>", self._window_menu)
        self._inner.bind("<Button-3>",  self._window_menu)

        # Keyboard zoom
        self.root.bind("<Control-equal>", lambda e: self._zoom_step(1))
        self.root.bind("<Control-minus>",  lambda e: self._zoom_step(-1))
        self.root.bind("<Control-0>",      lambda e: self._set_zoom(1.0))

        # Instant-add bar
        addbar = tk.Frame(self.root, bg=BG2, pady=4)
        addbar.pack(fill="x", padx=6, pady=(2,0))
        self._add_e = tk.Entry(
            addbar, bg=CARD, fg=TEXT, insertbackground=GREEN,
            relief="flat", font=("Segoe UI",9),
            highlightbackground=BORDER, highlightthickness=1)
        self._add_e.pack(side="left", fill="x", expand=True, ipady=4)
        self._add_e.bind("<Return>", lambda _: self._instant_add())

        self._cat_var = tk.StringVar(value=self._np_cats()[0])
        cm = tk.OptionMenu(addbar, self._cat_var, *self._np_cats())
        cm.config(bg=CARD, fg=LAVENDER, activebackground=LAVENDER,
                  activeforeground=BG, relief="flat", highlightthickness=0,
                  font=("Segoe UI",8), width=8)
        cm["menu"].config(bg=CARD, fg=TEXT)
        cm.pack(side="left", padx=(4,0))
        ok = tk.Label(addbar, text=" + ", bg=GREEN, fg=BG,
                      font=("Segoe UI",9,"bold"), cursor="hand2", padx=4)
        ok.pack(side="left", padx=(4,0))
        ok.bind("<Button-1>", lambda _: self._instant_add())

        # ── Multi-select toolbar ──────────────────────────────────────────
        mbar = tk.Frame(self.root, bg=BG, pady=2)
        mbar.pack(fill="x", padx=6)

        # Multi-select toggle
        self._multi_btn = tk.Label(
            mbar, text="☐ Multi", font=("Segoe UI",8),
            fg=DIM, bg=CARD, padx=6, pady=2, cursor="hand2")
        self._multi_btn.pack(side="left", padx=(0,3))
        self._multi_btn.bind("<Button-1>", lambda _: self._toggle_multi())

        # Join mode selector
        self._join_btn = tk.Label(
            mbar, text="join: space", font=("Segoe UI",7),
            fg=DIM, bg=CARD, padx=6, pady=2, cursor="hand2")
        self._join_btn.pack(side="left", padx=(0,3))
        self._join_btn.bind("<Button-1>", lambda _: self._cycle_join())

        # Copy selected
        self._copy_sel_btn = tk.Label(
            mbar, text="📋 Copy sel", font=("Segoe UI",7),
            fg=DIM, bg=CARD, padx=6, pady=2, cursor="hand2")
        self._copy_sel_btn.pack(side="left", padx=(0,3))
        self._copy_sel_btn.bind("<Button-1>", lambda _: self._copy_selected())

        # Clear clipboard
        clr = tk.Label(mbar, text="🗑 Clear", font=("Segoe UI",7),
                        fg=DIM, bg=CARD, padx=6, pady=2, cursor="hand2")
        clr.pack(side="left", padx=(0,3))
        clr.bind("<Button-1>", lambda _: self._clear_clipboard())

        # Selected count
        self._sel_count = tk.Label(
            mbar, text="", font=("Segoe UI",7), fg=DIM, bg=BG)
        self._sel_count.pack(side="right", padx=4)

        # Footer: status + zoom + resize grip
        foot = tk.Frame(self.root, bg=BG2, height=24)
        foot.pack(fill="x")
        foot.pack_propagate(False)

        self._status = tk.Label(foot, text="click → clipboard",
                                font=("Segoe UI",7), fg=DIM, bg=BG2)
        self._status.pack(side="left", padx=6)

        for ftxt, fcmd, fcol in [("📤", self._export_json, TEAL),
                                  ("📥", self._import_json, LAVENDER)]:
            fb = tk.Label(foot, text=ftxt, font=("Segoe UI",9),
                          fg=fcol, bg=BG2, cursor="hand2", padx=3)
            fb.pack(side="left")
            fb.bind("<Button-1>", lambda e, fn=fcmd: fn())

        # Zoom controls
        zm_frame = tk.Frame(foot, bg=BG2)
        zm_frame.pack(side="right", padx=(0,20))
        for txt, delta in [("−", -1), ("+", 1)]:
            b = tk.Label(zm_frame, text=txt, font=("Consolas",10,"bold"),
                         fg=LAVENDER, bg=BG2, cursor="hand2", padx=4)
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, d=delta: self._zoom_step(d))
        self._zoom_lbl = tk.Label(zm_frame, text=self._zoom_str(),
                                  font=("Segoe UI",7), fg=DIM, bg=BG2, width=4)
        self._zoom_lbl.pack(side="left")
        self._zoom_lbl.bind("<Button-1>", lambda _: self._set_zoom(1.0))  # click = reset

        # Resize grip ◢
        grip = tk.Canvas(foot, width=16, height=16, bg=BG2,
                         highlightthickness=0, cursor="size_nw_se")
        grip.pack(side="right")
        grip.create_line(12,2,2,12, fill=DIM,    width=1)
        grip.create_line(14,4,4,14, fill=DIM,    width=1)
        grip.create_line(14,8,8,14, fill=BORDER, width=1)
        grip.bind("<Button-1>",        self._resize_start)
        grip.bind("<B1-Motion>",       self._resize_move)
        grip.bind("<ButtonRelease-1>", self._resize_end)

    # ── Placeholder ───────────────────────────────────────────────────────
    def _set_ph(self):
        self._search_e.insert(0, "Search phrases…")
        self._search_e.config(fg=DIM)
        self._ph_active = True

    def _ph_in(self, _):
        if self._ph_active:
            self._search_e.delete(0,"end")
            self._search_e.config(fg=TEXT)
            self._ph_active = False

    def _ph_out(self, _):
        if not self._search_e.get():
            self._set_ph()

    def _get_q(self):
        v = self._search_var.get().strip().lower()
        return "" if self._ph_active or v in ("","search phrases…") else v

    # ── Render ────────────────────────────────────────────────────────────
    def _render(self):
        if not hasattr(self, "_inner"):
            return
        for w in self._inner.winfo_children():
            w.destroy()
        self._photos.clear()

        query     = self._get_q()
        collapsed = set(self.cfg.get("collapsed",[]))
        suffix    = self.cfg.get("suffix"," ")
        zm        = self._zoom

        inner_w  = max(120, self._w - 28)
        cell_w   = z(68, zm)
        ncols    = max(2, inner_w // cell_w)
        cell_h   = z(72, zm)
        icon_sz  = z(44, zm)
        font_sz  = max(6, z(7, zm))
        cat_font = max(7, z(8, zm))
        emoji_sz = max(12, z(20, zm))
        wrap     = max(40, cell_w - 10)

        for cat in self.cfg["categories"]:
            cname   = cat["name"]
            color   = cat["color"]
            phrases = list(cat["phrases"])
            is_pin  = cat.get("_pinned_bucket", False)

            if query:
                phrases = [p for p in phrases if query in p["text"].lower()]
                if not phrases:
                    continue
            else:
                if not phrases and is_pin:
                    continue

            is_col = (cname in collapsed) and not query

            # Category header
            hdr = tk.Frame(self._inner, bg=BG)
            hdr.pack(fill="x", padx=6, pady=(6,1))
            sq = tk.Canvas(hdr, width=12, height=12, bg=BG, highlightthickness=0)
            sq.pack(side="left")
            sq.create_rectangle(0,0,11,11, fill=color, outline="")
            icon_ch = "⭐" if is_pin else ("▸" if is_col else "▾")
            lbl = tk.Label(hdr, text=f" {icon_ch} {cname}",
                           font=("Segoe UI",cat_font,"bold"), fg=TEXT, bg=BG,
                           cursor="hand2")
            lbl.pack(side="left")
            cnt = tk.Label(hdr, text=f" {len(phrases)} ",
                           font=("Segoe UI",max(6,cat_font-1)), fg=BG,
                           bg=color, padx=3)
            cnt.pack(side="left", padx=4)

            def _toggle(cn=cname, ip=is_pin):
                if ip: return
                c = self.cfg.setdefault("collapsed",[])
                if cn in c: c.remove(cn)
                else:       c.append(cn)
                save_config(self.cfg)
                self._render()

            for w in (hdr, lbl, sq, cnt):
                w.bind("<Button-1>", lambda e, t=_toggle: t())

            if is_col:
                continue

            # Tile grid
            grid = tk.Frame(self._inner, bg=BG)
            grid.pack(fill="x", padx=6, pady=(0,2))
            for i in range(ncols):
                grid.columnconfigure(i, weight=1)

            for i, phrase in enumerate(phrases):
                text   = phrase["text"]
                emoji  = phrase.get("emoji","")
                img_p  = phrase.get("image")
                col_i  = i % ncols
                row_i  = i // ncols

                cell = tk.Frame(grid, bg=CARD, width=cell_w, height=cell_h,
                                highlightbackground=BORDER, highlightthickness=1)
                cell.grid(row=row_i, column=col_i, padx=2, pady=2, sticky="nsew")
                cell.grid_propagate(False)

                # ── Icon area ─────────────────────────────────────────────
                if img_p and Path(img_p).exists():
                    pil = make_image_tile(img_p, icon_sz)
                    if pil:
                        ph = ImageTk.PhotoImage(pil)
                        self._photos.append(ph)
                        icon_w = tk.Label(cell, image=ph, bg=CARD)
                        icon_w.pack(pady=(4,1))
                    else:
                        emoji = emoji or abbrev(text)[:1]  # fallback
                        icon_w = tk.Label(cell, text=emoji,
                                         font=("Segoe UI Emoji", emoji_sz),
                                         bg=CARD)
                        icon_w.pack(pady=(4,1))
                elif emoji:
                    icon_w = tk.Label(cell, text=emoji,
                                      font=("Segoe UI Emoji", emoji_sz),
                                      bg=CARD)
                    icon_w.pack(pady=(4,1))
                else:
                    pil = make_letter_tile(abbrev(text), color, icon_sz)
                    ph  = ImageTk.PhotoImage(pil)
                    self._photos.append(ph)
                    icon_w = tk.Label(cell, image=ph, bg=CARD)
                    icon_w.pack(pady=(4,1))

                # ── Label ─────────────────────────────────────────────────
                tl = tk.Label(cell, text=text, bg=CARD, fg=TEXT,
                              font=("Segoe UI Emoji", font_sz),
                              wraplength=wrap, justify="center", cursor="hand2")
                tl.pack(fill="x", padx=2, pady=(0,2))

                # ── Bindings ──────────────────────────────────────────────
                is_sel = text in self._selected
                sel_bg = "#2a1a4a" if is_sel else CARD  # purple tint if selected

                if is_sel:
                    for w in (cell, icon_w, tl): w.config(bg=sel_bg)
                    cell.config(highlightbackground=LAV)

                def _click(e, p=text, s=suffix, c=cell, iw=icon_w, tl_=tl):
                    if self._multi:
                        # Multi-select: toggle this phrase
                        if p in self._selected:
                            self._selected.remove(p)
                            for w in (c, iw, tl_): w.config(bg=CARD)
                            c.config(highlightbackground=BORDER)
                        else:
                            self._selected.append(p)
                            for w in (c, iw, tl_): w.config(bg="#2a1a4a")
                            c.config(highlightbackground=LAV)
                        self._update_sel_count()
                    else:
                        # Single: copy immediately
                        copy_clip(self.root, p + s)
                        self._flash(p)

                def _enter(e, c=cell, iw=icon_w, t=tl):
                    for w in (c, iw, t): w.config(bg=CARD_HI)

                def _leave(e, c=cell, iw=icon_w, t=tl, p=text):
                    bg = "#2a1a4a" if (self._multi and p in self._selected) else CARD
                    for w in (c, iw, t): w.config(bg=bg)

                def _rclick(e, p=phrase, cn=cname):
                    self._phrase_menu(e, p, cn)

                for w in (cell, icon_w, tl):
                    w.bind("<Button-1>", _click)
                    w.bind("<Enter>",    _enter)
                    w.bind("<Leave>",    _leave)
                    w.bind("<Button-3>", _rclick)

        self.root.update_idletasks()

    # ── Flash ─────────────────────────────────────────────────────────────
    def _flash(self, phrase):
        s = phrase if len(phrase) <= 24 else phrase[:22]+"…"
        self._status.config(text=f'✓ "{s}"', fg=GREEN)
        if self._flash_id: self.root.after_cancel(self._flash_id)
        self._flash_id = self.root.after(2200, lambda: self._status.config(
            text="click → clipboard", fg=DIM))

    # ── Multi-select controls ────────────────────────────────────────────
    def _toggle_multi(self):
        self._multi = not self._multi
        if self._multi:
            self._multi_btn.config(text="☑ Multi", fg=LAV, bg="#2a1a4a")
            self._selected.clear()
            self._flash("Multi-select ON — click tiles to select")
        else:
            self._multi_btn.config(text="☐ Multi", fg=DIM, bg=CARD)
            self._selected.clear()
            self._flash("Multi-select OFF")
        self._update_sel_count()
        self._render()

    def _cycle_join(self):
        modes = [(" ", "space"), (", ", "comma"), ("\n", "newline"), (" → ", "arrow"), (" | ", "pipe")]
        cur_join = self._join
        idx = 0
        for i, (sep, _) in enumerate(modes):
            if sep == cur_join:
                idx = i
                break
        idx = (idx + 1) % len(modes)
        self._join = modes[idx][0]
        self._join_btn.config(text=f"join: {modes[idx][1]}")

    def _copy_selected(self):
        if not self._selected:
            self._flash("Nothing selected")
            return
        combined = self._join.join(self._selected)
        copy_clip(self.root, combined)
        n = len(self._selected)
        self._flash(f"Copied {n} phrases")

    def _clear_clipboard(self):
        self.root.clipboard_clear()
        self.root.update()
        self._flash("Clipboard cleared")

    def _update_sel_count(self):
        n = len(self._selected)
        if n > 0:
            self._sel_count.config(text=f"{n} selected", fg=LAV)
        else:
            self._sel_count.config(text="", fg=DIM)

    # ── Phrase context menu ───────────────────────────────────────────────
    def _phrase_menu(self, event, phrase, cat_name):
        text      = phrase["text"]
        is_pinned = text in self._pinned_texts()
        m = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT,
                    activebackground=LAVENDER, activeforeground=BG, relief="flat")
        m.add_command(label="Copy",
                      command=lambda: self._do_copy(text))
        m.add_command(label="Copy  + comma",
                      command=lambda: self._do_copy(text+", "))
        m.add_command(label="Copy  + ellipsis",
                      command=lambda: self._do_copy(text+"… "))
        m.add_separator()
        if is_pinned:
            m.add_command(label="★ Unpin",
                          command=lambda: self._unpin(text))
        else:
            m.add_command(label="☆ Pin to Favourites",
                          command=lambda: self._pin(text))
        m.add_separator()
        m.add_command(label="✏️  Edit phrase / emoji / image",
                      command=lambda: self._edit_dialog(phrase, cat_name))
        m.add_command(label="🗑  Delete",
                      command=lambda: self._delete(text, cat_name))
        m.add_separator()
        m.add_command(label="⟳  Restart Linker",
                      command=self._restart)
        m.tk_popup(event.x_root, event.y_root)

    # ── Window-level context menu (right-click on background) ─────────────
    def _window_menu(self, event):
        m = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT,
                    activebackground=LAVENDER, activeforeground=BG, relief="flat")
        m.add_command(label="Zoom in   Ctrl+=",  command=lambda: self._zoom_step(1))
        m.add_command(label="Zoom out  Ctrl+−",  command=lambda: self._zoom_step(-1))
        m.add_command(label="Reset zoom  Ctrl+0", command=lambda: self._set_zoom(1.0))
        m.add_separator()
        m.add_command(label="📤  Export JSON  (for free LLM)", command=self._export_json)
        m.add_command(label="📥  Import JSON  (from LLM)",     command=self._import_json)
        m.add_separator()
        m.add_command(label="⟳  Restart Linker", command=self._restart)
        m.add_command(label="✕  Quit",            command=self._quit)
        m.tk_popup(event.x_root, event.y_root)

    # ── Export JSON ───────────────────────────────────────────────────────
    def _export_json(self):
        # Build clean export — categories + phrases only (no internal flags)
        export_cats = []
        for cat in self.cfg["categories"]:
            if cat.get("_pinned_bucket"):
                continue          # skip internal pinned bucket
            export_cats.append({
                "name":    cat["name"],
                "color":   cat["color"],
                "phrases": [{"text": p["text"], "emoji": p.get("emoji",""),
                             "image": p.get("image")}
                            for p in cat["phrases"]],
            })

        export_obj = {"categories": export_cats}
        pretty     = json.dumps(export_obj, indent=2, ensure_ascii=False)

        # Save to file alongside config
        export_path = SCRIPT_DIR / "linker_export.json"
        export_path.write_text(pretty, encoding="utf-8")

        # Also copy to clipboard with LLM prompt wrapper
        prompt = (
            "Here is my Linker phrase collection as JSON.\n"
            "Please reorganise the phrases into the most logical categories, "
            "fix any duplicates, suggest better emojis if appropriate, "
            "and return the SAME JSON structure with the same fields "
            "(categories array, each with name/color/phrases). "
            "Keep all existing phrases — don't remove any. "
            "You may rename categories or move phrases between them.\n\n"
            + pretty
        )
        copy_clip(self.root, prompt)

        # Show confirmation dialog
        dlg = tk.Toplevel(self.root)
        dlg.title("Exported")
        dlg.configure(bg=BG)
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        x = self.root.winfo_x() - 320
        if x < 0: x = self.root.winfo_x() + self._w + 6
        dlg.geometry(f"310x260+{x}+{self.root.winfo_y()}")

        tk.Label(dlg, text="  📤  Exported", bg=BG2, fg=GREEN,
                 font=("Segoe UI",9,"bold"), anchor="w").pack(fill="x", ipady=6)

        info = (
            f"Saved to:  linker_export.json\n\n"
            f"Clipboard now contains the JSON wrapped in a prompt "
            f"ready to paste into any free LLM (ChatGPT, Gemini, etc.).\n\n"
            f"After the LLM reorganises it, copy the JSON it returns "
            f"and use  📥 Import JSON  to load it back in live."
        )
        tk.Label(dlg, text=info, bg=BG, fg=TEXT,
                 font=("Segoe UI",9), wraplength=280,
                 justify="left", anchor="nw").pack(padx=14, pady=10, fill="x")

        # Show the raw JSON in a scrollable box
        tf = tk.Frame(dlg, bg=CARD)
        tf.pack(fill="both", expand=True, padx=10, pady=(0,8))
        txt = tk.Text(tf, bg=CARD, fg=DIM, font=("Consolas",7),
                      wrap="none", height=6, relief="flat")
        txt.insert("1.0", pretty[:600] + ("…" if len(pretty)>600 else ""))
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True, padx=4, pady=4)

        cb = tk.Label(dlg, text="Close", bg=BG2, fg=DIM,
                      font=("Segoe UI",8), cursor="hand2", pady=4)
        cb.pack(fill="x")
        cb.bind("<Button-1>", lambda _: dlg.destroy())

    # ── Import JSON ───────────────────────────────────────────────────────
    def _import_json(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Import JSON")
        dlg.configure(bg=BG)
        dlg.attributes("-topmost", True)
        dlg.resizable(True, True)
        x = self.root.winfo_x() - 340
        if x < 0: x = self.root.winfo_x() + self._w + 6
        dlg.geometry(f"330x420+{x}+{self.root.winfo_y()}")

        tk.Label(dlg, text="  📥  Import JSON from LLM", bg=BG2, fg=LAVENDER,
                 font=("Segoe UI",9,"bold"), anchor="w").pack(fill="x", ipady=6)
        tk.Label(dlg,
                 text="Paste the JSON the LLM returned below.\n"
                      "Existing Pinned phrases are kept. Everything else is replaced.",
                 bg=BG, fg=DIM, font=("Segoe UI",8),
                 wraplength=300, justify="left").pack(padx=10, pady=(6,4), anchor="w")

        # Text area
        tf = tk.Frame(dlg, bg=CARD)
        tf.pack(fill="both", expand=True, padx=10, pady=4)
        txt = tk.Text(tf, bg=CARD, fg=TEXT, insertbackground=LAVENDER,
                      font=("Consolas",8), wrap="none", relief="flat")
        vsb = tk.Scrollbar(tf, orient="vertical",   command=txt.yview, width=5)
        hsb = tk.Scrollbar(tf, orient="horizontal", command=txt.xview, width=5)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        txt.pack(fill="both", expand=True, padx=4, pady=4)
        txt.focus_set()

        status_lbl = tk.Label(dlg, text="", bg=BG, fg=DIM,
                              font=("Segoe UI",8), wraplength=300)
        status_lbl.pack(padx=10, pady=(0,4))

        def _do_import():
            raw = txt.get("1.0", "end").strip()
            # Strip markdown fences if LLM wrapped it
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(
                    l for l in lines
                    if not l.strip().startswith("```")
                )
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                status_lbl.config(text=f"❌ Invalid JSON: {e}", fg=RED)
                return

            new_cats = data.get("categories")
            if not isinstance(new_cats, list):
                status_lbl.config(text="❌ JSON must have a 'categories' array.", fg=RED)
                return

            # Normalise phrases in incoming data
            for cat in new_cats:
                cat["phrases"] = _migrate_phrases(cat.get("phrases", []))
                cat.pop("_pinned_bucket", None)   # never import this flag

            # Keep existing pinned bucket intact
            pinned = next(
                (c for c in self.cfg["categories"] if c.get("_pinned_bucket")),
                dict(PINNED_CAT)
            )

            # Replace categories, prepend pinned
            self.cfg["categories"] = [pinned] + new_cats
            save_config(self.cfg)   # ← permanent save
            self._render()          # ← live update

            n_phrases = sum(len(c["phrases"]) for c in new_cats)
            status_lbl.config(
                text=f"✓ Imported {len(new_cats)} categories, {n_phrases} phrases. Saved.",
                fg=GREEN)
            dlg.after(1800, dlg.destroy)

        btnrow = tk.Frame(dlg, bg=BG)
        btnrow.pack(fill="x", padx=10, pady=(0,10))
        ib = tk.Label(btnrow, text="Import & Save", bg=LAVENDER, fg=BG,
                      font=("Segoe UI",9,"bold"), padx=16, pady=5, cursor="hand2")
        ib.pack(side="left")
        ib.bind("<Button-1>", lambda _: _do_import())
        xb = tk.Label(btnrow, text="Cancel", bg=CARD, fg=DIM,
                      font=("Segoe UI",9), padx=12, pady=5, cursor="hand2")
        xb.pack(side="left", padx=(8,0))
        xb.bind("<Button-1>", lambda _: dlg.destroy())
        # Ctrl+Enter also triggers import
        txt.bind("<Control-Return>", lambda _: _do_import())

    def _do_copy(self, text):
        copy_clip(self.root, text)
        self._flash(text.strip(" .,…"))

    # ── Restart ───────────────────────────────────────────────────────────
    def _restart(self):
        self.cfg["pos"]  = [self.root.winfo_x(), self.root.winfo_y()]
        self.cfg["size"] = [self._w, self._h]
        self.cfg["zoom"] = self._zoom
        save_config(self.cfg)
        subprocess.Popen(
            [str(PYTHONW), str(SCRIPT_DIR / "linker.py")],
            creationflags=0x00000008,
            cwd=str(SCRIPT_DIR))
        if self._tray: self._tray.stop()
        self.root.destroy()

    # ── Pin / Unpin ───────────────────────────────────────────────────────
    def _pinned_bucket(self):
        for c in self.cfg["categories"]:
            if c.get("_pinned_bucket"):
                return c
        return None

    def _pinned_texts(self):
        b = self._pinned_bucket()
        return [p["text"] for p in b["phrases"]] if b else []

    def _pin(self, text):
        b = self._pinned_bucket()
        if not b: return
        if text not in [p["text"] for p in b["phrases"]]:
            b["phrases"].append(_p(text))
            save_config(self.cfg)
            self._render()

    def _unpin(self, text):
        b = self._pinned_bucket()
        if not b: return
        b["phrases"] = [p for p in b["phrases"] if p["text"] != text]
        save_config(self.cfg)
        self._render()

    # ── Instant add ───────────────────────────────────────────────────────
    def _np_cats(self):
        return [c["name"] for c in self.cfg["categories"]
                if not c.get("_pinned_bucket")]

    def _instant_add(self):
        text = self._add_e.get().strip()
        if not text: return
        # Detect leading emoji
        emoji = ""
        if text and not text[0].isascii():
            emoji = text[0]
            text  = text[1:].strip()
        if not text: return
        cat_t = self._cat_var.get()
        for cat in self.cfg["categories"]:
            if cat["name"] == cat_t:
                if text not in [p["text"] for p in cat["phrases"]]:
                    cat["phrases"].append(_p(text, emoji))
                break
        save_config(self.cfg)
        self._add_e.delete(0,"end")
        self._render()
        self._flash(f"Added: {text}")

    # ── Delete ────────────────────────────────────────────────────────────
    def _delete(self, text, cat_name):
        for cat in self.cfg["categories"]:
            if cat["name"] == cat_name:
                cat["phrases"] = [p for p in cat["phrases"] if p["text"] != text]
                break
        self._unpin(text)
        save_config(self.cfg)
        self._render()

    # ── Edit dialog ───────────────────────────────────────────────────────
    def _edit_dialog(self, phrase, cat_name):
        text  = phrase["text"]
        emoji = phrase.get("emoji","")
        img_p = phrase.get("image","") or ""

        dlg = tk.Toplevel(self.root)
        dlg.title("Edit Phrase")
        dlg.configure(bg=BG)
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        x = self.root.winfo_x() - 310
        if x < 0: x = self.root.winfo_x() + self._w + 6
        dlg.geometry(f"300x290+{x}+{self.root.winfo_y()}")

        def row(label, widget_fn):
            tk.Label(dlg, text=label, bg=BG, fg=DIM,
                     font=("Segoe UI",8)).pack(anchor="w", padx=12, pady=(8,1))
            return widget_fn()

        pe = row("Phrase text:", lambda: _entry(dlg, text))
        ee = row("Emoji icon (paste one emoji):", lambda: _entry(dlg, emoji))
        ie = row("Image path (optional):", lambda: _entry(dlg, img_p))

        tk.Label(dlg, text="Category:", bg=BG, fg=DIM,
                 font=("Segoe UI",8)).pack(anchor="w", padx=12, pady=(8,1))
        cats = self._np_cats()
        cv = tk.StringVar(value=cat_name if cat_name in cats else cats[0])
        cm = tk.OptionMenu(dlg, cv, *cats)
        cm.config(bg=CARD, fg=TEXT, activebackground=LAVENDER,
                  activeforeground=BG, relief="flat", highlightthickness=0)
        cm["menu"].config(bg=CARD, fg=TEXT)
        cm.pack(anchor="w", padx=12)

        def _save():
            new_text  = pe.get().strip()
            new_emoji = ee.get().strip()
            new_img   = ie.get().strip() or None
            new_cat   = cv.get()
            if not new_text: return
            # Remove from old cat
            for cat in self.cfg["categories"]:
                if cat["name"] == cat_name:
                    cat["phrases"] = [p for p in cat["phrases"] if p["text"] != text]
                    break
            # Update pinned if present
            b = self._pinned_bucket()
            if b:
                for p in b["phrases"]:
                    if p["text"] == text:
                        p["text"]  = new_text
                        p["emoji"] = new_emoji
                        p["image"] = new_img
            # Add to new cat
            for cat in self.cfg["categories"]:
                if cat["name"] == new_cat:
                    cat["phrases"].append(_p(new_text, new_emoji, new_img))
                    break
            save_config(self.cfg)
            self._render()
            dlg.destroy()

        btnrow = tk.Frame(dlg, bg=BG)
        btnrow.pack(fill="x", padx=12, pady=10)
        sb = tk.Label(btnrow, text="Save", bg=LAVENDER, fg=BG,
                      font=("Segoe UI",9,"bold"), padx=16, pady=4, cursor="hand2")
        sb.pack(side="left")
        sb.bind("<Button-1>", lambda _: _save())
        xb = tk.Label(btnrow, text="Cancel", bg=CARD, fg=DIM,
                      font=("Segoe UI",9), padx=12, pady=4, cursor="hand2")
        xb.pack(side="left", padx=(8,0))
        xb.bind("<Button-1>", lambda _: dlg.destroy())
        pe.bind("<Return>", lambda _: _save())
        pe.focus_set()

    # ── AI suggest ────────────────────────────────────────────────────────
    def _ai_suggest(self):
        api_key, model = load_api()
        if not api_key:
            self._flash("No API key — add to kidlin_config.json")
            return

        # Find the ✨ button and set it to spinner
        for w in self._bar.winfo_children():
            if isinstance(w, tk.Label) and "✨" in str(w.cget("text")):
                w.config(text=" ⏳ ", fg=PEACH)
                self._suggest_w = w
                break

        def _run():
            try:
                b64 = take_screenshot_b64()
                import anthropic
                c = anthropic.Anthropic(api_key=api_key)
                msg = c.messages.create(
                    model=model,
                    max_tokens=300,
                    messages=[{"role":"user","content":[
                        {"type":"image","source":{"type":"base64",
                         "media_type":"image/jpeg","data":b64}},
                        {"type":"text","text":(
                            "You see this user's desktop. Suggest 10 SHORT connector "
                            "phrases they'd say to link thoughts mid-sentence — "
                            "like 'and then', 'the thing is', 'going back to'. "
                            "Return ONLY a JSON array of objects: "
                            "[{\"text\":\"and then\",\"emoji\":\"➡️\"},...]. "
                            "No markdown, no explanation."
                        )},
                    ]}],
                )
                raw = msg.content[0].text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"): raw = raw[4:]
                suggestions = json.loads(raw)
                # Ensure correct format
                normed = []
                for s in suggestions:
                    if isinstance(s, str):
                        normed.append({"text":s,"emoji":""})
                    elif isinstance(s, dict):
                        normed.append({"text":s.get("text",s.get("phrase","")),
                                       "emoji":s.get("emoji","")})
                self.root.after(0, lambda: self._show_suggestions(normed))
            except Exception as ex:
                self.root.after(0, lambda: self._flash(f"AI error: {ex}"))
            finally:
                self.root.after(0, self._reset_suggest_btn)

        threading.Thread(target=_run, daemon=True).start()

    def _reset_suggest_btn(self):
        try:
            if hasattr(self, "_suggest_w"):
                self._suggest_w.config(text=" ✨ ", fg=YELLOW)
        except Exception:
            pass

    def _show_suggestions(self, suggestions):
        if not suggestions:
            self._flash("No suggestions returned")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("AI Suggestions")
        dlg.configure(bg=BG)
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        x = self.root.winfo_x() - 280
        if x < 0: x = self.root.winfo_x() + self._w + 6
        dlg.geometry(f"272x{min(80 + len(suggestions)*40, 500)}+{x}+{self.root.winfo_y()}")

        tk.Label(dlg, text="  ✨ Desktop suggestions",
                 bg=BG2, fg=YELLOW, font=("Segoe UI",9,"bold"), anchor="w"
                 ).pack(fill="x", ipady=6)
        tk.Label(dlg, text="  + add  ·  ★ pin  ·  right-click to choose cat",
                 bg=BG, fg=DIM, font=("Segoe UI",7)).pack(fill="x")

        frame = tk.Frame(dlg, bg=BG)
        frame.pack(fill="both", expand=True, padx=8, pady=6)

        cats = self._np_cats()
        add_to = tk.StringVar(value="Casual" if "Casual" in cats else cats[0])
        cm = tk.OptionMenu(frame, add_to, *cats)
        cm.config(bg=CARD, fg=LAVENDER, activebackground=LAVENDER,
                  activeforeground=BG, relief="flat", highlightthickness=0,
                  font=("Segoe UI",8))
        cm["menu"].config(bg=CARD, fg=TEXT)
        cm.pack(anchor="w", pady=(0,6))

        for s in suggestions:
            txt = s.get("text","")
            emj = s.get("emoji","")
            row = tk.Frame(frame, bg=CARD, pady=3)
            row.pack(fill="x", pady=1)
            if emj:
                tk.Label(row, text=emj, bg=CARD,
                         font=("Segoe UI Emoji",12), padx=4).pack(side="left")
            lbl = tk.Label(row, text=txt, bg=CARD, fg=TEXT,
                           font=("Segoe UI",9), anchor="w")
            lbl.pack(side="left", fill="x", expand=True, padx=(0,4))

            def _add(p=txt, e=emj):
                for cat in self.cfg["categories"]:
                    if cat["name"] == add_to.get():
                        if p not in [x["text"] for x in cat["phrases"]]:
                            cat["phrases"].append(_p(p, e))
                        break
                save_config(self.cfg)
                self._render()
                self._flash(f"Added: {p}")

            pin_btn = tk.Label(row, text="★", bg=CARD, fg=YELLOW,
                               font=("Segoe UI",9), cursor="hand2", padx=4)
            pin_btn.pack(side="right")
            pin_btn.bind("<Button-1>", lambda e, p=txt, em=emj: (
                self._pin_with_emoji(p, em),
                self._flash(f"Pinned: {p}")))

            add_btn = tk.Label(row, text="+", bg=GREEN, fg=BG,
                               font=("Segoe UI",9,"bold"), cursor="hand2",
                               padx=6, pady=0)
            add_btn.pack(side="right", padx=(0,4))
            add_btn.bind("<Button-1>", lambda e, fn=_add: fn())

            for w in (row, lbl):
                w.bind("<Enter>", lambda e,r=row,l=lbl: (r.config(bg=CARD_HI),l.config(bg=CARD_HI)))
                w.bind("<Leave>", lambda e,r=row,l=lbl: (r.config(bg=CARD),l.config(bg=CARD)))

        tk.Label(dlg, text="Close", bg=BG2, fg=DIM, font=("Segoe UI",8),
                 cursor="hand2", pady=4).pack(fill="x").bind(
                     "<Button-1>", lambda _: dlg.destroy()) if False else None
        cb = tk.Label(dlg, text="Close", bg=BG2, fg=DIM,
                      font=("Segoe UI",8), cursor="hand2", pady=4)
        cb.pack(fill="x")
        cb.bind("<Button-1>", lambda _: dlg.destroy())

    def _pin_with_emoji(self, text, emoji):
        b = self._pinned_bucket()
        if not b: return
        if text not in [p["text"] for p in b["phrases"]]:
            b["phrases"].append(_p(text, emoji))
            save_config(self.cfg)
            self._render()

    # ── Zoom ──────────────────────────────────────────────────────────────
    def _zoom_str(self):
        return f"{int(self._zoom*100)}%"

    def _set_zoom(self, val):
        self._zoom = val
        self.cfg["zoom"] = val
        save_config(self.cfg)
        if hasattr(self, "_zoom_lbl"):
            self._zoom_lbl.config(text=self._zoom_str())
        self._render()

    def _zoom_step(self, direction):
        steps = ZOOM_STEPS
        try:
            idx = min(range(len(steps)),
                      key=lambda i: abs(steps[i]-self._zoom))
        except Exception:
            idx = 2
        idx = max(0, min(len(steps)-1, idx+direction))
        self._set_zoom(steps[idx])

    # ── Drag ──────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    # ── Resize ────────────────────────────────────────────────────────────
    MIN_W, MIN_H = 160, 300

    def _resize_start(self, e):
        self._rx, self._ry = e.x_root, e.y_root
        self._rw, self._rh = self.root.winfo_width(), self.root.winfo_height()

    def _resize_move(self, e):
        nw = max(self.MIN_W, self._rw + e.x_root - self._rx)
        nh = max(self.MIN_H, self._rh + e.y_root - self._ry)
        self._w, self._h = nw, nh
        self.root.geometry(f"{nw}x{nh}")
        self._render()

    def _resize_end(self, _):
        self.cfg["size"] = [self._w, self._h]
        save_config(self.cfg)

    # ── Scroll ────────────────────────────────────────────────────────────
    def _wheel(self, e):
        try: self._canvas.yview_scroll(-(e.delta//120), "units")
        except: pass

    # ── Tray ──────────────────────────────────────────────────────────────
    def _start_tray(self):
        img = make_tray_img()
        menu = pystray.Menu(
            pystray.MenuItem("Show",          lambda: self.root.after(0, self._show)),
            pystray.MenuItem("Export JSON",    lambda: self.root.after(0, self._export_json)),
            pystray.MenuItem("Import JSON",    lambda: self.root.after(0, self._import_json)),
            pystray.MenuItem("Restart",        lambda: self.root.after(0, self._restart)),
            pystray.MenuItem("Quit",           lambda: self.root.after(0, self._quit)),
        )
        self._tray = pystray.Icon("linker", img, "Linker", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _show(self):
        self.root.deiconify()
        self.root.lift()

    def _quit(self):
        self.cfg["pos"]  = [self.root.winfo_x(), self.root.winfo_y()]
        self.cfg["size"] = [self._w, self._h]
        self.cfg["zoom"] = self._zoom
        save_config(self.cfg)
        if self._tray: self._tray.stop()
        self.root.destroy()


# ── Entry widget helper ───────────────────────────────────────────────────────
def _entry(parent, value=""):
    e = tk.Entry(parent, bg=CARD, fg=TEXT, insertbackground=LAVENDER,
                 relief="flat", font=("Segoe UI",10),
                 highlightbackground=BORDER, highlightthickness=1)
    e.insert(0, value)
    e.pack(fill="x", padx=12, ipady=4)
    return e


if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("linker.py")
    LinkerApp()
