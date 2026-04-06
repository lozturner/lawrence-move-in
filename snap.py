"""Quick single-app screenshot. Usage: python snap.py script.py "Window Title" """
import subprocess, sys, os, time, win32gui, psutil
from PIL import Image
import mss

DIR = os.path.dirname(os.path.abspath(__file__))
THUMBS = os.path.join(DIR, "thumbnails")
PW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
script, match = sys.argv[1], sys.argv[2]

# Kill old
for p in psutil.process_iter(["pid","name","cmdline"]):
    try:
        cmd = p.info["cmdline"] or []
        if len(cmd)>1 and script in cmd[1] and "python" in (p.info["name"]or"").lower() and p.pid!=os.getpid():
            p.kill()
    except: pass
time.sleep(0.3)

# Launch
subprocess.Popen([PW, os.path.join(DIR,script)], creationflags=0x8, cwd=DIR)
print(f"Launched {script}")

# Find window by title (15s timeout)
hwnd = None
for _ in range(30):
    results = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if match.lower() in t.lower() and "Gallery" not in t:
                results.append((h,t))
        return True
    try: win32gui.EnumWindows(cb, None)
    except: pass
    if results:
        hwnd, title = results[0]
        print(f"Found: {title}")
        break
    time.sleep(0.5)

out = os.path.join(THUMBS, script.replace(".py",".png"))
if hwnd:
    try: win32gui.SetForegroundWindow(hwnd)
    except: pass
    time.sleep(0.4)
    x1,y1,x2,y2 = win32gui.GetWindowRect(hwnd)
    x1=max(0,x1-6); y1=max(0,y1-6); x2+=6; y2+=6
    with mss.mss() as sct:
        s = sct.grab({"left":x1,"top":y1,"width":x2-x1,"height":y2-y1})
        Image.frombytes("RGB",(s.width,s.height),s.rgb).resize((504,284),Image.LANCZOS).save(out,quality=92)
    print(f"OK: {out}")
else:
    print("No window, desktop fallback")
    with mss.mss() as sct:
        s = sct.grab(sct.monitors[1])
        Image.frombytes("RGB",(s.width,s.height),s.rgb).resize((504,284),Image.LANCZOS).save(out,quality=92)

# Kill
for p in psutil.process_iter(["pid","name","cmdline"]):
    try:
        cmd = p.info["cmdline"] or []
        if len(cmd)>1 and script in cmd[1] and "python" in (p.info["name"]or"").lower() and p.pid!=os.getpid():
            p.kill()
    except: pass
