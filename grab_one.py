"""Capture one app thumbnail. Usage: python grab_one.py <script.py> <title_match>"""
import subprocess, sys, os, time
import win32gui, win32process
import psutil
from PIL import Image
import mss

DIR = os.path.dirname(os.path.abspath(__file__))
THUMBS = os.path.join(DIR, "thumbnails")
PYTHONW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")

script = sys.argv[1]
title_match = sys.argv[2] if len(sys.argv) > 2 else ""

def kill(name):
    for p in psutil.process_iter(["pid","name","cmdline"]):
        try:
            cmd = p.info["cmdline"] or []
            if len(cmd)>1 and name in cmd[1] and "python" in (p.info["name"] or "").lower():
                if p.pid != os.getpid():
                    p.kill()
        except: pass

# Kill old instances
kill(script)
time.sleep(0.5)

# Launch
path = os.path.join(DIR, script)
proc = subprocess.Popen([PYTHONW, path], creationflags=0x00000008, cwd=DIR)
pid = proc.pid
print(f"Launched {script} PID={pid}")

# Find window by PID
hwnd = None
for _ in range(20):  # 10 seconds
    windows = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            try:
                _, wp = win32process.GetWindowThreadProcessId(h)
                if wp == pid:
                    t = win32gui.GetWindowText(h)
                    if t and len(t) > 1:
                        windows.append((h, t))
            except: pass
        return True
    try: win32gui.EnumWindows(cb, None)
    except: pass
    if windows:
        hwnd = windows[0][0]
        print(f"Found: '{windows[0][1]}'")
        break
    time.sleep(0.5)

# Also try by title if PID search failed
if not hwnd and title_match:
    for _ in range(10):
        found = []
        def cb2(h, _):
            if win32gui.IsWindowVisible(h):
                t = win32gui.GetWindowText(h)
                if title_match.lower() in t.lower():
                    found.append((h, t))
            return True
        try: win32gui.EnumWindows(cb2, None)
        except: pass
        if found:
            hwnd = found[0][0]
            print(f"Found by title: '{found[0][1]}'")
            break
        time.sleep(0.5)

if hwnd:
    try: win32gui.SetForegroundWindow(hwnd)
    except: pass
    time.sleep(0.5)
    rect = win32gui.GetWindowRect(hwnd)
    x1,y1,x2,y2 = rect
    x1=max(0,x1-8); y1=max(0,y1-8); x2+=8; y2+=8
    with mss.mss() as sct:
        shot = sct.grab({"left":x1,"top":y1,"width":x2-x1,"height":y2-y1})
        img = Image.frombytes("RGB",(shot.width,shot.height),shot.rgb)
        img = img.resize((504,284), Image.LANCZOS)
        out = os.path.join(THUMBS, script.replace(".py",".png"))
        img.save(out, quality=92)
        print(f"Saved {out}")
else:
    print("No window found — using desktop")
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB",(shot.width,shot.height),shot.rgb)
        img = img.resize((504,284), Image.LANCZOS)
        out = os.path.join(THUMBS, script.replace(".py",".png"))
        img.save(out, quality=92)
        print(f"Saved desktop fallback: {out}")

# Kill
kill(script)
try: proc.kill()
except: pass
print("Done")
