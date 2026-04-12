"""
Lawrence: Move In — WindowBot v2.0.0
LLM-powered window command chatbot. Understands natural language.
Learns skills from interactions. Sends button with code preview.
"""
__version__ = "2.0.0"
import selfclean; selfclean.ensure_single("windowbot.py")

import json, os, re, subprocess, threading, time, tkinter as tk
from tkinter import ttk
from pathlib import Path
import win32gui, win32con, win32process
import psutil, pystray
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_FILE = SCRIPT_DIR / "windowbot_skills.json"
CONFIG_FILE = SCRIPT_DIR / "kidlin_config.json"

# ── Actions — the things WindowBot can actually do ────────────────────────────
def _wins():
    r = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if t and len(t) > 2 and t not in ("Program Manager", "Default IME"):
                try: _, pid = win32process.GetWindowThreadProcessId(h); e = psutil.Process(pid).name()
                except: e = "?"
                r.append((h, t, e))
        return True
    try: win32gui.EnumWindows(cb, None)
    except: pass
    return r

def _fg(): return win32gui.GetForegroundWindow()
def _focus(h):
    try:
        if win32gui.IsIconic(h): win32gui.ShowWindow(h, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(h)
    except: pass
def _sw(): return win32gui.GetSystemMetrics(0)
def _sh(): return win32gui.GetSystemMetrics(1)

ACTIONS = {
    "list_windows": {
        "label": "List Windows", "code": "EnumWindows -> list visible",
        "fn": lambda: "\n".join(f"{t[:30]} ({e})" for _, t, e in _wins()[:8])
    },
    "swap": {
        "label": "Swap Windows", "code": "SetForegroundWindow(next_window)",
        "fn": lambda: next(((_focus(h), f"-> {t[:35]}")[1] for h, t, _ in _wins() if h != _fg() and "WindowBot" not in t), "No other window")
    },
    "alt_tab": {
        "label": "Alt+Tab", "code": "keybd_event(VK_MENU + VK_TAB)",
        "fn": lambda: (__import__('ctypes').windll.user32.keybd_event(0x12,0,0,0), __import__('ctypes').windll.user32.keybd_event(0x09,0,0,0), __import__('ctypes').windll.user32.keybd_event(0x09,0,2,0), __import__('ctypes').windll.user32.keybd_event(0x12,0,2,0), "Alt+Tab")[-1]
    },
    "window_info": {
        "label": "Window Info", "code": "GetWindowRect(GetForegroundWindow())",
        "fn": lambda: f"{win32gui.GetWindowText(_fg())[:25]}\n{win32gui.GetWindowRect(_fg())}"
    },
    "snap_top": {
        "label": "Snap Top", "code": "SetWindowPos(fg, 0, 0, sw, sh/2)",
        "fn": lambda: (win32gui.SetWindowPos(_fg(), 0, 0, 0, _sw(), _sh()//2, 0), "Snapped top")[1]
    },
    "snap_bottom": {
        "label": "Snap Bottom", "code": "SetWindowPos(fg, 0, sh/2, sw, sh/2)",
        "fn": lambda: (win32gui.SetWindowPos(_fg(), 0, 0, _sh()//2, _sw(), _sh()//2, 0), "Snapped bottom")[1]
    },
    "snap_left": {
        "label": "Move Left", "code": "SetWindowPos(fg, 0, 0, sw/2, sh)",
        "fn": lambda: (win32gui.SetWindowPos(_fg(), 0, 0, 0, _sw()//2, _sh(), 0), "Left")[1]
    },
    "snap_right": {
        "label": "Move Right", "code": "SetWindowPos(fg, sw/2, 0, sw/2, sh)",
        "fn": lambda: (win32gui.SetWindowPos(_fg(), 0, _sw()//2, 0, _sw()//2, _sh(), 0), "Right")[1]
    },
    "split_screen": {
        "label": "Split Screen", "code": "SetWindowPos(A, left_half) + SetWindowPos(B, right_half)",
        "fn": lambda: _do_split()
    },
    "maximize": {
        "label": "Maximise", "code": "ShowWindow(fg, SW_MAXIMIZE)",
        "fn": lambda: (win32gui.ShowWindow(_fg(), win32con.SW_MAXIMIZE), "Maximised")[1]
    },
    "minimize": {
        "label": "Minimise", "code": "ShowWindow(fg, SW_MINIMIZE)",
        "fn": lambda: (win32gui.ShowWindow(_fg(), win32con.SW_MINIMIZE), "Minimised")[1]
    },
    "restore": {
        "label": "Restore", "code": "ShowWindow(fg, SW_RESTORE)",
        "fn": lambda: (win32gui.ShowWindow(_fg(), win32con.SW_RESTORE), "Restored")[1]
    },
    "close_window": {
        "label": "Close Window", "code": "PostMessage(fg, WM_CLOSE)",
        "fn": lambda: _do_close()
    },
    "cascade": {
        "label": "Cascade All", "code": "CascadeWindows()",
        "fn": lambda: (__import__('ctypes').windll.user32.CascadeWindows(None, 0, None, 0, None), "Cascaded")[1]
    },
    "start_menu": {
        "label": "Start Menu", "code": "keybd_event(VK_LWIN)",
        "fn": lambda: (__import__('ctypes').windll.user32.keybd_event(0x5B, 0, 0, 0), __import__('ctypes').windll.user32.keybd_event(0x5B, 0, 2, 0), "Start menu toggled")[2]
    },
    "task_view": {
        "label": "Task View", "code": "keybd_event(VK_LWIN + VK_TAB)",
        "fn": lambda: (__import__('ctypes').windll.user32.keybd_event(0x5B,0,0,0), __import__('ctypes').windll.user32.keybd_event(0x09,0,0,0), __import__('ctypes').windll.user32.keybd_event(0x09,0,2,0), __import__('ctypes').windll.user32.keybd_event(0x5B,0,2,0), "Task View")[4]
    },
    "open_app": {
        "label": "Open App", "code": "os.startfile(app) / subprocess.Popen()",
        "fn": lambda: "Specify app name after 'open' — e.g. 'open notepad'"
    },
    "run_command": {
        "label": "Run Command", "code": "subprocess.Popen(cmd, shell=True)",
        "fn": lambda: "Specify command — e.g. 'run calc.exe'"
    },
    "focus_window": {
        "label": "Focus Window", "code": "SetForegroundWindow(hwnd_by_title)",
        "fn": lambda: "Specify window name — e.g. 'focus chrome'"
    },
    "unknown": {
        "label": "Unknown", "code": "# no matching action",
        "fn": lambda: "I don't know how to do that yet"
    },
}

# Dynamic action handlers (need arguments from LLM)
def _open_app(app_name):
    import subprocess, shutil
    app_name = app_name.strip().lower()
    # Common app mappings
    APP_MAP = {
        "notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe",
        "paint": "mspaint.exe", "explorer": "explorer.exe", "file explorer": "explorer.exe",
        "cmd": "cmd.exe", "command prompt": "cmd.exe", "terminal": "wt.exe",
        "powershell": "powershell.exe", "task manager": "taskmgr.exe",
        "settings": "ms-settings:", "control panel": "control.exe",
        "chrome": "chrome.exe", "edge": "msedge.exe", "firefox": "firefox.exe",
        "word": "winword.exe", "excel": "excel.exe", "outlook": "outlook.exe",
        "spotify": "spotify.exe", "discord": "discord.exe", "slack": "slack.exe",
        "teams": "teams.exe", "telegram": "telegram.exe",
        "vscode": "code.exe", "vs code": "code.exe", "code": "code.exe",
        "snipping tool": "snippingtool.exe", "snip": "snippingtool.exe",
        "start": "start_menu",
    }
    # Check direct mapping
    for key, exe in APP_MAP.items():
        if key in app_name:
            if exe == "start_menu":
                import ctypes
                ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
                return "Start menu opened"
            if exe.startswith("ms-"):
                os.startfile(exe)
                return f"Opened {key}"
            # Try to find and run it
            full = shutil.which(exe)
            if full:
                subprocess.Popen([full], creationflags=0x00000008)
                return f"Opened {key}"
            else:
                try:
                    os.startfile(exe)
                    return f"Opened {key}"
                except:
                    pass
    # Fallback — try os.startfile with the raw name
    try:
        os.startfile(app_name)
        return f"Opened {app_name}"
    except:
        return f"Can't find '{app_name}'"

def _focus_by_name(name):
    name_lower = name.strip().lower()
    for h, t, e in _wins():
        if name_lower in t.lower() or name_lower in e.lower():
            _focus(h)
            return f"Focused: {t[:35]}"
    return f"No window matching '{name}'"

def _do_split():
    w = [(h, t) for h, t, _ in _wins() if "WindowBot" not in t]
    if len(w) < 2: return "Need 2+ windows"
    win32gui.SetWindowPos(w[0][0], 0, 0, 0, _sw()//2, _sh(), 0)
    win32gui.SetWindowPos(w[1][0], 0, _sw()//2, 0, _sw()//2, _sh(), 0)
    return f"{w[0][1][:16]} | {w[1][1][:16]}"

def _do_close():
    h = _fg(); t = win32gui.GetWindowText(h)
    win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
    return f"Closed {t[:25]}"

# ── Skills bin — learned phrase -> action mappings ────────────────────────────
def load_skills():
    if SKILLS_FILE.exists():
        try:
            with open(SKILLS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"skills": [], "version": "1.0"}

def save_skills(data):
    try:
        with open(SKILLS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except: pass

def find_learned_skill(text):
    """Check if we've already learned what this phrase means."""
    data = load_skills()
    text_lower = text.lower().strip()
    for skill in data.get("skills", []):
        phrase = skill.get("phrase", "").lower()
        if phrase and (phrase in text_lower or text_lower in phrase):
            action_id = skill.get("action_id")
            if action_id in ACTIONS:
                return ACTIONS[action_id], skill
    return None, None

def learn_skill(phrase, action_id):
    """Save a phrase -> action mapping to the skills bin."""
    data = load_skills()
    # Don't duplicate
    for s in data.get("skills", []):
        if s.get("phrase", "").lower() == phrase.lower() and s.get("action_id") == action_id:
            return
    data.setdefault("skills", []).append({
        "phrase": phrase,
        "action_id": action_id,
        "learned_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "uses": 0,
    })
    save_skills(data)

def bump_skill_use(phrase):
    """Increment use count for a learned skill."""
    data = load_skills()
    for s in data.get("skills", []):
        if s.get("phrase", "").lower() == phrase.lower():
            s["uses"] = s.get("uses", 0) + 1
            break
    save_skills(data)

# ── LLM intent recognition ───────────────────────────────────────────────────
def load_api_key():
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
            return cfg.get("api_key", ""), cfg.get("model", "claude-sonnet-4-20250514")
    except:
        return "", "claude-sonnet-4-20250514"

ACTION_IDS = ", ".join(ACTIONS.keys())

SYSTEM_PROMPT = f"""You are WindowBot, a window management + app launcher for Windows 10.
The user speaks naturally. You respond with EXACTLY one JSON object, nothing else.

Available action IDs: {ACTION_IDS}

For open_app: include "arg" with the app name. E.g. "open notepad" -> {{"action_id":"open_app","arg":"notepad","explain":"Opening Notepad"}}
For focus_window: include "arg" with the window/app name. E.g. "go to chrome" -> {{"action_id":"focus_window","arg":"chrome","explain":"Focusing Chrome"}}
For run_command: include "arg" with the command. E.g. "run calc" -> {{"action_id":"run_command","arg":"calc.exe","explain":"Running calculator"}}
For everything else: {{"action_id":"snap_left","explain":"Snapping left"}}

IMPORTANT: "open the start button" = "start_menu". "open notepad" = "open_app" with arg "notepad".
"switch to chrome" or "go to chrome" = "focus_window" with arg "chrome".
Be generous. Never say "not supported". Always find the closest match.

Current open windows:
{{windows}}
"""

def ask_llm(text, callback):
    """Background thread: ask Claude what action this phrase maps to."""
    def _work():
        api_key, model = load_api_key()
        if not api_key:
            callback(None, "No API key in kidlin_config.json", "")
            return

        # Build context with current windows
        wins = _wins()
        win_list = "\n".join(f"- {t[:40]} ({e})" for _, t, e in wins[:10])
        system = SYSTEM_PROMPT.replace("{windows}", win_list)

        try:
            import urllib.request
            body = json.dumps({
                "model": model,
                "max_tokens": 100,
                "system": system,
                "messages": [{"role": "user", "content": text}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                })
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
                content = data["content"][0]["text"].strip()
                # Parse JSON from response
                # Handle potential markdown wrapping
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                result = json.loads(content)
                action_id = result.get("action_id", "unknown")
                explain = result.get("explain", "")
                arg = result.get("arg", "")
                callback(action_id, explain, arg)
        except Exception as e:
            callback(None, f"LLM error: {str(e)[:50]}", "")

    threading.Thread(target=_work, daemon=True).start()

# ── GUI ───────────────────────────────────────────────────────────────────────
class WindowBot:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("WindowBot v2")
        self.root.configure(bg="#1a1a2e")
        self.root.attributes("-topmost", True)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"280x140+{sw - 300}+{sh - 200}")
        self.root.resizable(False, False)
        self._pending_phrase = ""
        self._build()
        self._tray()

    def _build(self):
        # Header — draggable
        hdr = tk.Frame(self.root, bg="#16213e", height=16)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="WindowBot v2", font=("Consolas", 7, "bold"),
                 fg="#89b4fa", bg="#16213e").pack(side="left", padx=3)
        skills_data = load_skills()
        skill_count = len(skills_data.get("skills", []))
        tk.Label(hdr, text=f"{skill_count} skills", font=("Consolas", 6),
                 fg="#585b70", bg="#16213e").pack(side="right", padx=3)

        def _sd(e): self._dx, self._dy = e.x, e.y
        def _d(e): self.root.geometry(f"+{self.root.winfo_x()+e.x-self._dx}+{self.root.winfo_y()+e.y-self._dy}")
        hdr.bind("<Button-1>", _sd)
        hdr.bind("<B1-Motion>", _d)

        # Chat area
        self.chat = tk.Frame(self.root, bg="#1a1a2e")
        self.chat.pack(fill="both", expand=True, padx=4, pady=1)
        self.msg = tk.Label(self.chat, text="Say anything naturally...",
                             font=("Segoe UI", 7), fg="#a6adc8", bg="#1a1a2e",
                             wraplength=268, justify="left", anchor="nw")
        self.msg.pack(fill="both", expand=True)

        # Button area
        self.btns = tk.Frame(self.root, bg="#1a1a2e")
        self.btns.pack(fill="x", padx=4, pady=(0, 1))

        # Input + Send
        inp = tk.Frame(self.root, bg="#1a1a2e")
        inp.pack(fill="x", padx=4, pady=(0, 3))
        self.entry = tk.Entry(inp, font=("Segoe UI", 8), bg="#16213e", fg="#cdd6f4",
                               insertbackground="#89b4fa", relief="flat",
                               highlightthickness=1, highlightbackground="#313244",
                               highlightcolor="#89b4fa")
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self._submit)
        self.entry.focus_set()

        tk.Button(inp, text="Send", font=("Segoe UI", 7, "bold"),
                  fg="#1a1a2e", bg="#89b4fa", relief="flat", padx=6, pady=0,
                  cursor="hand2", command=lambda: self._submit(None)).pack(side="right", padx=(3, 0))

    def _submit(self, e):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._pending_phrase = text
        self.msg.config(text=f"> {text}", fg="#cdd6f4")

        # Step 1: Check learned skills bin
        action, skill = find_learned_skill(text)
        if action:
            bump_skill_use(text)
            self.msg.config(text=f"Skill: {action['label']}\n(learned from: \"{skill['phrase']}\")", fg="#f9e2af")
            self._show_action(action, skill.get("action_id", "unknown"))
            return

        # Step 2: No learned skill — ask Claude
        self.msg.config(text=f"> {text}\nThinking...", fg="#a6adc8")
        for w in self.btns.winfo_children():
            w.destroy()

        def _on_result(action_id, explain, arg):
            self.root.after(0, lambda: self._handle_llm_result(text, action_id, explain, arg))

        ask_llm(text, _on_result)

    def _handle_llm_result(self, phrase, action_id, explain, arg=""):
        if action_id is None:
            self.msg.config(text=f"Error: {explain}", fg="#f38ba8")
            return

        if action_id not in ACTIONS:
            action_id = "unknown"

        action = ACTIONS[action_id]

        if action_id == "unknown":
            self.msg.config(text=f"{explain or 'Not sure what to do.'}\nType something else?", fg="#f38ba8")
            return

        # For actions that need an argument, create a dynamic action with the arg baked in
        if action_id == "open_app" and arg:
            action = dict(action)
            action["fn"] = lambda a=arg: _open_app(a)
            action["label"] = f"Open {arg.title()}"
            action["code"] = f"os.startfile('{arg}')"
        elif action_id == "focus_window" and arg:
            action = dict(action)
            action["fn"] = lambda a=arg: _focus_by_name(a)
            action["label"] = f"Focus {arg.title()}"
            action["code"] = f"SetForegroundWindow(find('{arg}'))"
        elif action_id == "run_command" and arg:
            action = dict(action)
            action["fn"] = lambda a=arg: (subprocess.Popen(a, shell=True, creationflags=0x00000008), f"Running: {a}")[1]
            action["label"] = f"Run {arg}"
            action["code"] = f"subprocess.Popen('{arg}', shell=True)"

        # Show the matched action
        self.msg.config(text=f"{action['label']}: {explain}", fg="#a6e3a1")
        self._show_action(action, action_id)

        # Auto-learn this phrase -> action
        learn_skill(phrase, action_id)

    def _show_action(self, action, action_id):
        for w in self.btns.winfo_children():
            w.destroy()

        # Run button
        tk.Button(self.btns, text=f"# {action['label']}", font=("Segoe UI", 7, "bold"),
                  fg="#1a1a2e", bg="#a6e3a1", relief="flat", padx=5, pady=0,
                  cursor="hand2",
                  command=lambda: self._run(action)).pack(side="left", padx=(0, 2))

        # Code button
        tk.Button(self.btns, text="{ }", font=("Consolas", 7),
                  fg="#89b4fa", bg="#16213e", relief="flat", padx=3, pady=0,
                  cursor="hand2",
                  command=lambda: self.msg.config(
                      text=f"Code: {action['code']}\nAction: {action_id}",
                      fg="#89dceb")).pack(side="left", padx=(0, 2))

        # Forget button (if this was a learned skill)
        tk.Button(self.btns, text="x", font=("Consolas", 7),
                  fg="#f38ba8", bg="#16213e", relief="flat", padx=3, pady=0,
                  cursor="hand2",
                  command=lambda: self._forget(action_id)).pack(side="right")

    def _run(self, action):
        try:
            result = action["fn"]()
            self.msg.config(text=str(result), fg="#a6e3a1")
        except Exception as e:
            self.msg.config(text=f"Err: {e}", fg="#f38ba8")
        self.root.after(4000, lambda: self.msg.config(
            text="Say anything naturally...", fg="#a6adc8"))

    def _forget(self, action_id):
        """Remove the most recent learned skill for this action."""
        data = load_skills()
        phrase = self._pending_phrase.lower()
        data["skills"] = [s for s in data.get("skills", [])
                          if not (s.get("phrase", "").lower() == phrase
                                  and s.get("action_id") == action_id)]
        save_skills(data)
        self.msg.config(text="Forgotten. Try rephrasing.", fg="#f9e2af")
        for w in self.btns.winfo_children():
            w.destroy()

    def _tray(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([8, 8, 56, 56], radius=8, fill="#16213e", outline="#89b4fa", width=2)
        d.ellipse([18, 20, 28, 30], fill="#89b4fa")
        d.ellipse([36, 20, 46, 30], fill="#89b4fa")
        d.rounded_rectangle([20, 38, 44, 46], radius=3, fill="#a6e3a1")

        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda: self.root.after(0, lambda: (self.root.deiconify(), self.root.lift()))),
            pystray.MenuItem("Skills bin", lambda: self.root.after(0, self._show_skills)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: (self.tray.stop(), self.root.after(0, self.root.destroy))))
        self.tray = pystray.Icon("wb", img, f"WindowBot v{__version__}", menu=menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _show_skills(self):
        """Show all learned skills in a popup."""
        data = load_skills()
        skills = data.get("skills", [])
        if not skills:
            self.msg.config(text="No learned skills yet.\nJust talk to me.", fg="#f9e2af")
            return
        lines = []
        for s in skills[-8:]:
            action = ACTIONS.get(s.get("action_id"), {})
            label = action.get("label", "?")
            lines.append(f'"{s["phrase"][:20]}" -> {label} ({s.get("uses", 0)}x)')
        self.msg.config(text="\n".join(lines), fg="#89dceb")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.withdraw())
        self.root.mainloop()

class BotPrompt:
    """Dev companion — shows system prompt, skills, notes. Paste changes here."""
    def __init__(self, parent_root):
        self.win = tk.Toplevel(parent_root)
        self.win.title("Bot Prompt — Dev Panel")
        self.win.configure(bg="#1e1e2e")
        self.win.geometry("420x500+20+60")
        self.win.attributes("-topmost", True)

        # Header
        hdr = tk.Frame(self.win, bg="#2d2740", pady=6, padx=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Bot Prompt", font=("Consolas", 10, "bold"),
                 fg="#f9e2af", bg="#2d2740").pack(side="left")
        tk.Button(hdr, text="Reload", font=("Segoe UI", 7),
                  fg="#89b4fa", bg="#16213e", relief="flat", padx=8,
                  command=self._reload).pack(side="right")

        # Notebook (tabs)
        nb = ttk.Notebook(self.win)
        nb.pack(fill="both", expand=True, padx=4, pady=4)

        # Tab 1: System Prompt
        f1 = tk.Frame(nb, bg="#1e1e2e")
        nb.add(f1, text="System Prompt")
        self.prompt_text = tk.Text(f1, font=("Consolas", 8), bg="#16213e", fg="#cdd6f4",
                                    insertbackground="#89b4fa", relief="flat",
                                    wrap="word", highlightthickness=0)
        self.prompt_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Tab 2: Skills Bin
        f2 = tk.Frame(nb, bg="#1e1e2e")
        nb.add(f2, text="Skills")
        self.skills_text = tk.Text(f2, font=("Consolas", 8), bg="#16213e", fg="#cdd6f4",
                                    insertbackground="#89b4fa", relief="flat",
                                    wrap="word", highlightthickness=0)
        self.skills_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Tab 3: Actions
        f3 = tk.Frame(nb, bg="#1e1e2e")
        nb.add(f3, text="Actions")
        self.actions_text = tk.Text(f3, font=("Consolas", 8), bg="#16213e", fg="#cdd6f4",
                                     relief="flat", wrap="word", highlightthickness=0)
        self.actions_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Tab 4: Notes (user pastes changes here)
        f4 = tk.Frame(nb, bg="#1e1e2e")
        nb.add(f4, text="Notes")
        self.notes_text = tk.Text(f4, font=("Segoe UI", 9), bg="#16213e", fg="#cdd6f4",
                                   insertbackground="#89b4fa", relief="flat",
                                   wrap="word", highlightthickness=0)
        self.notes_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.notes_text.insert("1.0", "Paste changes, ideas, or feedback here.\nThis is your dev scratchpad.\n\n")

        # Save notes button
        btn_row = tk.Frame(self.win, bg="#1e1e2e", pady=4)
        btn_row.pack(fill="x", padx=4)
        tk.Button(btn_row, text="Save Notes", font=("Segoe UI", 8, "bold"),
                  fg="#1e1e2e", bg="#a6e3a1", relief="flat", padx=12, pady=2,
                  command=self._save_notes).pack(side="right", padx=4)
        tk.Button(btn_row, text="Export All", font=("Segoe UI", 8),
                  fg="#89b4fa", bg="#16213e", relief="flat", padx=10, pady=2,
                  command=self._export).pack(side="right")

        self._reload()

    def _reload(self):
        # System prompt
        wins = _wins()
        win_list = "\n".join(f"- {t[:40]} ({e})" for _, t, e in wins[:10])
        prompt = SYSTEM_PROMPT.replace("{windows}", win_list)
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", prompt)

        # Skills
        data = load_skills()
        self.skills_text.delete("1.0", "end")
        skills = data.get("skills", [])
        if skills:
            for s in skills:
                line = f'"{s["phrase"]}" -> {s["action_id"]} ({s.get("uses",0)}x)\n'
                self.skills_text.insert("end", line)
        else:
            self.skills_text.insert("1.0", "No learned skills yet.\nUse WindowBot to build them.\n")

        # Actions
        self.actions_text.delete("1.0", "end")
        for aid, a in ACTIONS.items():
            self.actions_text.insert("end", f"{aid}\n  label: {a['label']}\n  code: {a['code']}\n\n")

    def _save_notes(self):
        notes = self.notes_text.get("1.0", "end").strip()
        notes_file = SCRIPT_DIR / "windowbot_notes.txt"
        try:
            with open(notes_file, "w", encoding="utf-8") as f:
                f.write(notes)
        except: pass

    def _export(self):
        """Export everything to a single markdown file."""
        export_path = SCRIPT_DIR / "windowbot_export.md"
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                f.write("# WindowBot Dev Export\n\n")
                f.write("## System Prompt\n```\n")
                f.write(self.prompt_text.get("1.0", "end"))
                f.write("```\n\n## Skills\n```\n")
                f.write(self.skills_text.get("1.0", "end"))
                f.write("```\n\n## Actions\n```\n")
                f.write(self.actions_text.get("1.0", "end"))
                f.write("```\n\n## Notes\n")
                f.write(self.notes_text.get("1.0", "end"))
            os.startfile(str(export_path))
        except: pass


if __name__ == "__main__":
    bot = WindowBot()
    BotPrompt(bot.root)  # Dev panel launches alongside
    bot.run()
