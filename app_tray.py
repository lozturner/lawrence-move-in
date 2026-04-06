"""
Lawrence: Move In — App Tray v2.0.0
Fixed system tray icons with REAL icons from the actual executables.
"""
__version__ = "2.0.0"

import json, os, subprocess, sys, threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR  = Path(__file__).resolve().parent
ICONS_DIR   = SCRIPT_DIR / "icons"
CONFIG_PATH = SCRIPT_DIR / "app_tray_config.json"

DEFAULT_APPS = [
    {"name":"File Explorer", "icon":"explorer.ico",
     "path":"explorer.exe", "args":""},
    {"name":"Microsoft Edge", "icon":"edge.ico",
     "path":r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "args":""},
    {"name":"Google Chrome", "icon":"chrome.ico",
     "path":r"C:\Program Files\Google\Chrome\Application\chrome.exe", "args":""},
    {"name":"Perplexity", "icon":"perplexity.ico",
     "path":r"C:\Program Files\Google\Chrome\Application\chrome.exe",
     "args":"--app=https://perplexity.ai"},
    {"name":"Comet Browser", "icon":"comet.ico",
     "path":r"C:\Users\123\AppData\Local\Perplexity\Comet\Application\comet.exe", "args":""},
]

def load_config():
    if CONFIG_PATH.exists():
        try: return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except: pass
    cfg = {"apps": DEFAULT_APPS}
    save_config(cfg)
    return cfg

def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def load_icon(icon_name):
    p = ICONS_DIR / icon_name
    if p.exists():
        try: return Image.open(str(p))
        except: pass
    # Fallback
    img = Image.new("RGBA",(64,64),(100,100,100,255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4,4,59,59], radius=12, fill=(180,180,180))
    return img

def launch_app(app):
    path, args = app["path"], app.get("args","")
    try:
        if args:
            subprocess.Popen(f'"{path}" {args}', shell=True, creationflags=0x8)
        elif path.lower() == "explorer.exe":
            subprocess.Popen(["explorer.exe"], creationflags=0x8)
        else:
            subprocess.Popen([path], creationflags=0x8)
    except: pass

def make_launcher(app):
    def _fn(icon, item): launch_app(app)
    return _fn

def make_quitter():
    def _fn(icon, item): icon.stop()
    return _fn

def create_tray(app):
    icon_img = load_icon(app.get("icon",""))
    menu = pystray.Menu(
        pystray.MenuItem(f"Open {app['name']}", make_launcher(app)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", make_quitter()),
    )
    return pystray.Icon(f"apptray_{app['name']}", icon_img, app["name"], menu)

def main():
    cfg = load_config()
    for app in cfg["apps"]:
        p = app["path"]
        if p.lower() != "explorer.exe" and not os.path.exists(p):
            for alt in [p.replace("Program Files","Program Files (x86)"),
                        p.replace("Program Files (x86)","Program Files")]:
                if os.path.exists(alt):
                    app["path"] = alt; break

    threads, icons = [], []
    for app in cfg["apps"]:
        icon = create_tray(app)
        icons.append(icon)
        t = threading.Thread(target=icon.run, daemon=True)
        t.start(); threads.append(t)
    try:
        for t in threads: t.join()
    except KeyboardInterrupt:
        for i in icons: i.stop()

if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("app_tray.py")
    main()
