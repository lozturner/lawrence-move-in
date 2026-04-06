"""
Lawrence: Move In — Voice Sort v1.1.0
Auto-intercepts text from EVERYWHERE:
  1. Clipboard watcher (auto-detects ANY copy)
  2. Global hotkey Ctrl+Shift+V to sort whatever's on clipboard
  3. Manual paste button + text input box for typing/editing
  4. Catches Ctrl+C system-wide and processes after a beat
AI categorises, titles, files by type. Always on top.
"""

__version__ = "1.1.0"

import ctypes
import ctypes.wintypes
import json
import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

import win32clipboard
import win32con
import keyboard  # global hotkey hooks

# --- Config ---
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "kidlin_config.json"
SORT_DIR = SCRIPT_DIR / "voice_sorted"
LOG_PATH = SORT_DIR / "_all.jsonl"

# --- Categories ---
CATEGORIES = {
    "task":        {"colour": "#f38ba8", "label": "TASK"},
    "thought":     {"colour": "#89b4fa", "label": "THOUGHT"},
    "idea":        {"colour": "#cba6f7", "label": "IDEA"},
    "note":        {"colour": "#a6e3a1", "label": "NOTE"},
    "question":    {"colour": "#f9e2af", "label": "QUESTION"},
    "reminder":    {"colour": "#fab387", "label": "REMINDER"},
    "musing":      {"colour": "#b4befe", "label": "MUSING"},
    "reaction":    {"colour": "#f5c2e7", "label": "REACTION"},
    "argument":    {"colour": "#f38ba8", "label": "ARGUMENT"},
    "poignant":    {"colour": "#94e2d5", "label": "POIGNANT"},
    "vent":        {"colour": "#f38ba8", "label": "VENT"},
    "instruction": {"colour": "#89dceb", "label": "INSTRUCTION"},
    "observation": {"colour": "#a6e3a1", "label": "OBSERVATION"},
    "adhd":        {"colour": "#5a5a80", "label": "ADHD"},
}

BG = "#0a0a14"
BG2 = "#12122a"
CARD = "#1a1a3a"
BORDER = "#2a2a50"
TEXT = "#cdd6f4"
DIM = "#5a5a80"
ACCENT = "#cba6f7"
GREEN = "#a6e3a1"
BLUE = "#89b4fa"
PEACH = "#fab387"
RED = "#f38ba8"
TEAL = "#94e2d5"

LEARNED_TAGS_PATH = SORT_DIR / "_learned_tags.json"

def load_learned_tags():
    try:
        if LEARNED_TAGS_PATH.exists():
            with open(LEARNED_TAGS_PATH) as f:
                return json.load(f)
    except: pass
    return []

def save_learned_tags(tags):
    try:
        with open(LEARNED_TAGS_PATH, "w") as f:
            json.dump(sorted(set(tags)), f, indent=2)
    except: pass

def get_system_prompt():
    learned = load_learned_tags()
    extra = ""
    if learned:
        extra = f'\n\nThe user has also created these custom tags in the past — use them when relevant: {", ".join(learned)}'

    return f"""You are a voice note categoriser for someone with ADHD who dumps thoughts via voice all day.

Given a transcribed voice note, respond with ONLY a JSON object:
{{
  "categories": ["primary_tag", "optional_second_tag"],
  "suggested_tags": ["2-3 extra tags you think apply but aren't sure about"],
  "title": "short 3-8 word title",
  "actionable": true/false,
  "priority": "high/medium/low/none",
  "summary": "1 sentence max",
  "relates_to": "your best guess what topic/project/person this relates to, or empty string"
}}

Built-in categories: task, thought, idea, note, question, reminder, musing, reaction, argument, poignant, vent, instruction, observation, adhd{extra}

Rules:
- "categories" = 1-3 tags that DEFINITELY apply. Can be built-in or custom.
- "suggested_tags" = 2-3 more you think MIGHT apply — user confirms these.
- "relates_to" = brief context guess (a project name, person, topic).
- "task" = something to do. "thought" = thinking aloud. "adhd" = tangent/noise.
- "poignant" = genuinely insightful. "musing" = pondering without conclusion.
- Title must be specific. "Fix auth bug" not "Technical thought".
- Return ONLY JSON."""


def load_api():
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                c = json.load(f)
                return c.get("api_key", ""), c.get("model", "claude-sonnet-4-20250514")
    except Exception:
        pass
    return "", "claude-sonnet-4-20250514"


def get_clipboard():
    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return data.strip()
        win32clipboard.CloseClipboard()
    except Exception:
        try: win32clipboard.CloseClipboard()
        except: pass
    return ""


class VoiceSort:
    def __init__(self):
        self.root = None
        self._alive = True
        self._drag_x = 0
        self._drag_y = 0
        self._last_clip = ""
        self._entries = []
        self._processing = False
        self._paused = False
        self._seen_texts = set()  # dedup
        SORT_DIR.mkdir(exist_ok=True)

    def run(self):
        self._last_clip = get_clipboard()
        if self._last_clip:
            self._seen_texts.add(self._last_clip[:200])

        self.root = tk.Tk()
        self.root.title(f"Voice Sort v{__version__}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg=BG)

        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"380x500+20+60")

        self._build()
        self._make_draggable()

        # === THREE INTERCEPTION METHODS ===

        # 1. Clipboard polling (catches ALL copies from any app)
        self._poll_clipboard()

        # 2. Global hotkey: Ctrl+Shift+V = force-sort clipboard now
        keyboard.add_hotkey("ctrl+shift+v", self._hotkey_sort, suppress=False)

        # 3. Global hook: after any Ctrl+C, wait 300ms then check clipboard
        keyboard.add_hotkey("ctrl+c", self._on_ctrl_c, suppress=False)

        self.root.mainloop()

    def _build(self):
        # Header
        hdr = tk.Frame(self.root, bg=BG2, height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self.header = hdr

        tk.Label(hdr, text="Voice Sort v1.1", font=("Segoe UI", 9, "bold"),
                 fg=ACCENT, bg=BG2).pack(side="left", padx=8)

        self.status_lbl = tk.Label(hdr, text="● Listening",
                                   font=("Segoe UI", 7, "bold"), fg=GREEN, bg=BG2)
        self.status_lbl.pack(side="left", padx=6)

        # Right buttons
        for txt, cmd in [("✕", self._quit), ("Pause", self._toggle_pause)]:
            b = tk.Label(hdr, text=txt, font=("Segoe UI", 7 if txt != "✕" else 9),
                         fg=DIM, bg=BG2 if txt == "✕" else "#1a1a3a",
                         padx=6, pady=1, cursor="hand2")
            b.pack(side="right", padx=2, pady=2)
            b.bind("<Button-1>", lambda e, c=cmd, bb=b: c(bb))
            if txt == "✕":
                b.bind("<Enter>", lambda e, bb=b: bb.config(fg=RED))
                b.bind("<Leave>", lambda e, bb=b: bb.config(fg=DIM))
            if txt == "Pause":
                self.pause_btn = b

        # === Input box (type or paste directly) ===
        input_frame = tk.Frame(self.root, bg=BG)
        input_frame.pack(fill="x", padx=6, pady=(6, 2))

        tk.Label(input_frame, text="Type, paste, or just copy anywhere — I catch it all",
                 font=("Segoe UI", 7), fg=DIM, bg=BG).pack(anchor="w")

        entry_row = tk.Frame(input_frame, bg=BORDER)
        entry_row.pack(fill="x", pady=(2, 0))

        self.input_entry = tk.Text(entry_row, height=3, bg=CARD, fg=TEXT,
                                   insertbackground=TEXT, font=("Segoe UI", 9),
                                   relief="flat", wrap="word", padx=6, pady=4)
        self.input_entry.pack(fill="x", padx=1, pady=1)
        self.input_entry.bind("<Control-Return>", lambda e: self._submit_input())

        btn_row = tk.Frame(input_frame, bg=BG)
        btn_row.pack(fill="x", pady=(2, 0))

        sort_btn = tk.Label(btn_row, text="Sort this", font=("Segoe UI", 8, "bold"),
                            fg=BG, bg=ACCENT, padx=10, pady=3, cursor="hand2")
        sort_btn.pack(side="left")
        sort_btn.bind("<Button-1>", lambda e: self._submit_input())
        sort_btn.bind("<Enter>", lambda e: sort_btn.config(bg=BLUE))
        sort_btn.bind("<Leave>", lambda e: sort_btn.config(bg=ACCENT))

        paste_btn = tk.Label(btn_row, text="Paste & Sort", font=("Segoe UI", 8),
                             fg=BLUE, bg=CARD, padx=8, pady=3, cursor="hand2")
        paste_btn.pack(side="left", padx=4)
        paste_btn.bind("<Button-1>", lambda e: self._paste_and_sort())

        tk.Label(btn_row, text="Ctrl+Shift+V anywhere", font=("Segoe UI", 6),
                 fg=DIM, bg=BG).pack(side="right")

        # Stats
        self.stats_lbl = tk.Label(self.root, text="0 sorted",
                                  font=("Segoe UI", 7), fg=DIM, bg=BG)
        self.stats_lbl.pack(fill="x", padx=8)

        # Entries list
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=4, pady=2)

        self.canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview, width=5)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=BG)
        self.cw = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.config(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self.cw, width=e.width))
        self.canvas.bind("<Enter>",
                         lambda e: self.root.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>",
                         lambda e: self.root.unbind_all("<MouseWheel>"))

        # Bottom bar
        bottom = tk.Frame(self.root, bg=BG2, height=22)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        tk.Label(bottom, text="Open folder", font=("Segoe UI", 7),
                 fg=BLUE, bg=BG2, cursor="hand2").pack(side="left", padx=8)
        bottom.winfo_children()[-1].bind("<Button-1>",
                                          lambda e: os.startfile(str(SORT_DIR)))

        tk.Label(bottom, text="Export", font=("Segoe UI", 7),
                 fg=PEACH, bg=BG2, cursor="hand2").pack(side="right", padx=8)
        bottom.winfo_children()[-1].bind("<Button-1>", lambda e: self._export())

    def _wheel(self, e):
        try: self.canvas.yview_scroll(-(e.delta // 120), "units")
        except: pass

    def _make_draggable(self):
        def start(e): self._drag_x, self._drag_y = e.x, e.y
        def drag(e):
            self.root.geometry(
                f"+{self.root.winfo_x()+e.x-self._drag_x}"
                f"+{self.root.winfo_y()+e.y-self._drag_y}")
        for w in (self.header,) + tuple(self.header.winfo_children()):
            w.bind("<Button-1>", start)
            w.bind("<B1-Motion>", drag)

    # === INTERCEPTION ===

    def _poll_clipboard(self):
        """Method 1: poll clipboard every 600ms for changes."""
        if not self._alive: return
        if not self._paused and not self._processing:
            try:
                clip = get_clipboard()
                if clip and len(clip) > 10 and clip != self._last_clip:
                    sig = clip[:200]
                    if sig not in self._seen_texts:
                        self._last_clip = clip
                        self._seen_texts.add(sig)
                        self._ingest(clip, source="clipboard")
            except Exception:
                pass
        self.root.after(600, self._poll_clipboard)

    def _on_ctrl_c(self):
        """Method 2: global Ctrl+C hook — wait for clipboard to update, then check."""
        if self._paused: return
        def delayed():
            time.sleep(0.4)  # wait for clipboard to populate
            if not self._alive or self._processing: return
            clip = get_clipboard()
            if clip and len(clip) > 10:
                sig = clip[:200]
                if sig not in self._seen_texts:
                    self._last_clip = clip
                    self._seen_texts.add(sig)
                    self.root.after(0, lambda: self._ingest(clip, source="ctrl+c"))
        threading.Thread(target=delayed, daemon=True).start()

    def _hotkey_sort(self):
        """Method 3: Ctrl+Shift+V — force sort whatever's on clipboard."""
        if self._paused or self._processing: return
        clip = get_clipboard()
        if clip and len(clip) > 3:
            self._seen_texts.add(clip[:200])
            self._last_clip = clip
            self.root.after(0, lambda: self._ingest(clip, source="hotkey"))

    def _submit_input(self):
        """Method 4: manual text entry."""
        text = self.input_entry.get("1.0", "end").strip()
        if text and len(text) > 3:
            self.input_entry.delete("1.0", "end")
            self._ingest(text, source="typed")

    def _paste_and_sort(self):
        """Method 5: paste button — grab clipboard into input then sort."""
        clip = get_clipboard()
        if clip:
            self.input_entry.delete("1.0", "end")
            self.input_entry.insert("1.0", clip)
            self._submit_input()

    # === AI SORT ===

    def _ingest(self, text, source="unknown"):
        if self._processing: return
        self._processing = True
        self.status_lbl.config(text=f"● Sorting ({source})...", fg=PEACH)

        def do_sort():
            api_key, model = load_api()
            if not api_key:
                entry = self._make_entry(["note"], [], "No API key", False, "none",
                                         text[:100], text, source, "")
                self.root.after(0, lambda: self._on_sorted(entry))
                return

            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                msg = client.messages.create(
                    model=model, max_tokens=300, system=get_system_prompt(),
                    messages=[{"role": "user", "content": text}],
                )
                reply = msg.content[0].text.strip()
                if reply.startswith("```"):
                    reply = reply.split("```")[1]
                    if reply.startswith("json"): reply = reply[4:]
                r = json.loads(reply)

                # Handle multi-tag response
                cats = r.get("categories", [r.get("category", "note")])
                if isinstance(cats, str): cats = [cats]
                suggested = r.get("suggested_tags", [])
                relates_to = r.get("relates_to", "")

                entry = self._make_entry(
                    cats, suggested, r.get("title", "Untitled"),
                    r.get("actionable", False), r.get("priority", "none"),
                    r.get("summary", text[:100]), text, source, relates_to)
            except Exception as e:
                entry = self._make_entry(["note"], [], f"Error: {str(e)[:30]}",
                                         False, "none", text[:100], text, source, "")

            self.root.after(0, lambda: self._on_sorted(entry))

        threading.Thread(target=do_sort, daemon=True).start()

    def _make_entry(self, categories, suggested, title, actionable, priority,
                    summary, raw, source, relates_to):
        return {
            "categories": categories,        # confirmed tags
            "suggested": suggested,           # AI suggested, user confirms
            "user_tags": [],                  # user-added custom tags
            "title": title,
            "actionable": actionable,
            "priority": priority,
            "summary": summary,
            "raw": raw[:500],
            "source": source,
            "relates_to": relates_to,         # context: project/person/topic
            "todo_with": "",                  # user fills in: additional context
            "time": datetime.now().isoformat(),
        }

    def _on_sorted(self, entry):
        self._processing = False
        self._entries.insert(0, entry)
        self.status_lbl.config(text="● Listening", fg=GREEN)

        # Save JSONL
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except: pass

        # Save to category files (one per tag)
        for tag in entry.get("categories", ["note"]):
            cat_file = SORT_DIR / f"{tag}.md"
            try:
                with open(cat_file, "a", encoding="utf-8") as f:
                    ts = entry["time"][:16].replace("T", " ")
                    all_tags = " ".join(f"[{t}]" for t in entry.get("categories", []))
                    f.write(f"## {entry['title']} ({ts}) [{entry['source']}]\n")
                    f.write(f"Tags: {all_tags}\n")
                    if entry.get("relates_to"):
                        f.write(f"Re: {entry['relates_to']}\n")
                    if entry["actionable"]:
                        f.write(f"**Priority:** {entry['priority']}\n")
                    f.write(f"{entry['summary']}\n\n> {entry['raw'][:300]}\n\n---\n\n")
            except: pass

        self._update_stats()
        self._render()

    # === RENDER ===

    def _render(self):
        for w in self.inner.winfo_children():
            w.destroy()
        for entry in self._entries[:25]:
            self._draw_entry(entry)
        self.root.update_idletasks()
        self.canvas.yview_moveto(0.0)

    def _draw_entry(self, entry):
        primary_cat = entry.get("categories", ["note"])[0] if entry.get("categories") else "note"
        cat = CATEGORIES.get(primary_cat, CATEGORIES["note"])

        frame = tk.Frame(self.inner, bg=CARD)
        frame.pack(fill="x", padx=4, pady=3)

        tk.Frame(frame, bg=cat["colour"], width=4).pack(side="left", fill="y")

        inner = tk.Frame(frame, bg=CARD)
        inner.pack(fill="x", padx=8, pady=6)

        # === YOUR ORIGINAL TEXT (verbatim, prominent) ===
        raw = entry.get("raw", "")
        if raw:
            tk.Label(inner, text=raw, font=("Segoe UI", 10),
                     fg=TEXT, bg=CARD, wraplength=330, justify="left",
                     anchor="nw").pack(fill="x", pady=(0, 4))

        # === CONFIRMED TAGS (coloured badges) ===
        tags_row = tk.Frame(inner, bg=CARD)
        tags_row.pack(fill="x", pady=(0, 2))

        all_tags = list(entry.get("categories", [])) + list(entry.get("user_tags", []))
        for tag in all_tags:
            tc = CATEGORIES.get(tag, {}).get("colour", ACCENT)
            tl = CATEGORIES.get(tag, {}).get("label", tag.upper())
            tk.Label(tags_row, text=f" {tl} ", font=("Consolas", 7, "bold"),
                     fg="#0a0a14", bg=tc).pack(side="left", padx=(0, 3))

        if entry.get("actionable"):
            pc = {"high": RED, "medium": PEACH, "low": BLUE}.get(entry.get("priority",""), DIM)
            tk.Label(tags_row, text=f" {entry['priority'].upper()} ",
                     font=("Consolas", 6, "bold"), fg="#0a0a14", bg=pc).pack(side="left", padx=2)

        tk.Label(tags_row, text=entry["time"][11:16], font=("Segoe UI", 7),
                 fg=DIM, bg=CARD).pack(side="right")

        # === SUGGESTED TAGS (dimmer, click to confirm) ===
        suggested = entry.get("suggested", [])
        if suggested:
            sug_row = tk.Frame(inner, bg=CARD)
            sug_row.pack(fill="x", pady=(0, 2))
            tk.Label(sug_row, text="also?", font=("Segoe UI", 6),
                     fg=DIM, bg=CARD).pack(side="left", padx=(0, 4))
            for stag in suggested:
                sl = CATEGORIES.get(stag, {}).get("label", stag.upper())
                sc = CATEGORIES.get(stag, {}).get("colour", DIM)
                sbtn = tk.Label(sug_row, text=f" +{sl} ", font=("Consolas", 6),
                                fg=sc, bg=BORDER, cursor="hand2", padx=2)
                sbtn.pack(side="left", padx=(0, 2))
                sbtn.bind("<Button-1>", lambda e, ent=entry, t=stag: self._confirm_tag(ent, t))

        # === AI TITLE + RELATES TO ===
        meta_row = tk.Frame(inner, bg=CARD)
        meta_row.pack(fill="x")

        tk.Label(meta_row, text=entry.get("title", ""), font=("Segoe UI", 8),
                 fg=DIM, bg=CARD).pack(side="left")

        relates = entry.get("relates_to", "")
        if relates:
            tk.Label(meta_row, text=f"re: {relates}", font=("Segoe UI", 7),
                     fg=TEAL, bg=CARD).pack(side="right")

        # === TO DO WITH (user context box) ===
        tdw = entry.get("todo_with", "")

        tdw_row = tk.Frame(inner, bg=CARD)
        tdw_row.pack(fill="x", pady=(3, 0))

        if tdw:
            tk.Label(tdw_row, text=f"Context: {tdw}", font=("Segoe UI", 8),
                     fg=PEACH, bg=CARD, wraplength=320, anchor="w", justify="left").pack(fill="x")
        else:
            ctx_btn = tk.Label(tdw_row, text="+ add context", font=("Segoe UI", 7),
                               fg=BORDER, bg=CARD, cursor="hand2")
            ctx_btn.pack(side="left")
            ctx_btn.bind("<Button-1>", lambda e, ent=entry: self._add_context(ent))

        # === ADD CUSTOM TAG button ===
        add_tag_btn = tk.Label(tdw_row, text="+ tag", font=("Segoe UI", 7),
                               fg=BORDER, bg=CARD, cursor="hand2")
        add_tag_btn.pack(side="right")
        add_tag_btn.bind("<Button-1>", lambda e, ent=entry: self._add_custom_tag(ent))

    def _confirm_tag(self, entry, tag):
        """Move a suggested tag into confirmed categories."""
        if tag not in entry.get("categories", []):
            entry.setdefault("categories", []).append(tag)
        if tag in entry.get("suggested", []):
            entry["suggested"].remove(tag)
        # Learn this tag for future prompts
        learned = load_learned_tags()
        if tag not in learned and tag not in CATEGORIES:
            learned.append(tag)
            save_learned_tags(learned)
        self._render()

    def _add_custom_tag(self, entry):
        """Pop up a small input for user to type a new tag."""
        win = tk.Toplevel(self.root)
        win.title("Add tag")
        win.configure(bg=BG)
        win.geometry("240x80")
        win.attributes("-topmost", True)
        win.resizable(False, False)

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=10, pady=10)

        tk.Label(row, text="Tag:", font=("Segoe UI", 9), fg=TEXT, bg=BG).pack(side="left")
        var = tk.StringVar()
        e = tk.Entry(row, textvariable=var, bg=CARD, fg=TEXT, insertbackground=TEXT,
                     font=("Segoe UI", 10), relief="flat")
        e.pack(side="left", fill="x", expand=True, padx=6, ipady=3)
        e.focus_set()

        def submit(event=None):
            tag = var.get().strip().lower().replace(" ", "-")
            if tag:
                entry.setdefault("user_tags", []).append(tag)
                # Also add to the entry's categories for filing
                entry.setdefault("categories", []).append(tag)
                # Learn it
                learned = load_learned_tags()
                if tag not in learned:
                    learned.append(tag)
                    save_learned_tags(learned)
                # Add to CATEGORIES runtime if new
                if tag not in CATEGORIES:
                    CATEGORIES[tag] = {"colour": ACCENT, "label": tag.upper()}
            win.destroy()
            self._render()

        e.bind("<Return>", submit)
        tk.Label(row, text="Enter", font=("Segoe UI", 7), fg=DIM, bg=BG).pack(side="right")

    def _add_context(self, entry):
        """Pop up input for 'to do with' / additional context."""
        win = tk.Toplevel(self.root)
        win.title("Add context")
        win.configure(bg=BG)
        win.geometry("300x100")
        win.attributes("-topmost", True)
        win.resizable(False, False)

        tk.Label(win, text="What's this to do with?",
                 font=("Segoe UI", 9, "bold"), fg=PEACH, bg=BG).pack(padx=10, pady=(8, 4), anchor="w")

        var = tk.StringVar()
        e = tk.Entry(win, textvariable=var, bg=CARD, fg=TEXT, insertbackground=TEXT,
                     font=("Segoe UI", 10), relief="flat")
        e.pack(fill="x", padx=10, ipady=4)
        e.focus_set()

        def submit(event=None):
            ctx = var.get().strip()
            if ctx:
                entry["todo_with"] = ctx
            win.destroy()
            self._render()

        e.bind("<Return>", submit)

    def _update_stats(self):
        today = datetime.now().strftime("%Y-%m-%d")
        n = sum(1 for e in self._entries if e["time"].startswith(today))
        cats = {}
        for e in self._entries:
            for c in e.get("categories", []):
                cats[c] = cats.get(c, 0) + 1
        top = sorted(cats.items(), key=lambda x: -x[1])[:3]
        self.stats_lbl.config(text=f"{n} today | " + " ".join(f"{c}:{v}" for c, v in top))

    def _export(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = SORT_DIR / f"summary_{ts}.md"
        lines = [f"# Voice Sort — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"]
        by_cat = {}
        for e in self._entries:
            by_cat.setdefault(e["category"], []).append(e)
        for ck, entries in sorted(by_cat.items()):
            cl = CATEGORIES.get(ck, CATEGORIES["note"])["label"]
            lines.append(f"## {cl} ({len(entries)})\n\n")
            for e in entries:
                lines.append(f"- **{e['title']}** ({e['time'][11:16]}): {e['summary']}\n")
            lines.append("\n")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        self.status_lbl.config(text=f"Exported {path.name}", fg=TEAL)
        self.root.after(3000, lambda: self.status_lbl.config(text="● Listening", fg=GREEN))

    def _toggle_pause(self, btn=None):
        self._paused = not self._paused
        if self._paused:
            self.status_lbl.config(text="● Paused", fg="#f9e2af")
            if btn: btn.config(text="Resume")
        else:
            self.status_lbl.config(text="● Listening", fg=GREEN)
            if btn: btn.config(text="Pause")

    def _quit(self, btn=None):
        self._alive = False
        keyboard.unhook_all()
        try: self.root.destroy()
        except: pass
        os._exit(0)


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("voicesort.py")
    VoiceSort().run()
