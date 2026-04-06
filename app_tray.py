"""
Lawrence: Move In — App Tray v1.0.0
Fixed tray icons for common apps. The tray doesn't shuffle.
Click the right-click menu → opens the app. Always there, always in the same spot.
"""
__version__ = "1.0.0"

import json, os, subprocess, sys, threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "app_tray_config.json"

# ── Default apps to pin to tray ──────────────────────────────────────────────
DEFAULT_APPS = [
    {
        "name": "File Explorer",
        "abbrev": "FE",
        "color": [255, 203, 107],
        "path": "explorer.exe",
        "args": "",
    },
    {
        "name": "Edge",
        "abbrev": "ED",
        "color": [0, 120, 215],
        "path": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "args": "",
    },
    {
        "name": "Chrome",
        "abbrev": "CR",
        "color": [66, 133, 244],
        "path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "args": "",
    },
    {
        "name": "Perplexity",
        "abbrev": "PX",
        "color": [32, 191, 163],
        "path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "args": "--app=https://perplexity.ai",
    },
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

def make_icon(abbrev, color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r, g, b = color
    d.rounded_rectangle([4, 4, 59, 59], radius=12, fill=(r, g, b, 255))
    try:    fnt = ImageFont.truetype("consola.ttf", 18)
    except: fnt = ImageFont.load_default()
    bb = d.textbbox((0, 0), abbrev, font=fnt)
    d.text(((64-(bb[2]-bb[0]))//2, (64-(bb[3]-bb[1]))//2),
           abbrev, fill="#0a0a14", font=fnt)
    return img

def launch_app(app):
    path = app["path"]
    args = app.get("args", "")
    try:
        if args:
            subprocess.Popen(f'"{path}" {args}', shell=True, creationflags=0x8)
        else:
            if path.lower() == "explorer.exe":
                subprocess.Popen(["explorer.exe"], creationflags=0x8)
            else:
                subprocess.Popen([path], creationflags=0x8)
    except Exception as e:
        print(f"Failed to launch {app['name']}: {e}")

def _make_launcher(app):
    """Return a 2-arg callback that launches the app."""
    def _fn(icon, item):
        launch_app(app)
    return _fn

def _make_quitter():
    def _fn(icon, item):
        icon.stop()
    return _fn

def create_tray(app):
    """Create one tray icon for one app."""
    icon_img = make_icon(app["abbrev"], app["color"])

    menu = pystray.Menu(
        pystray.MenuItem(f"Open {app['name']}", _make_launcher(app)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit this icon", _make_quitter()),
    )

    icon = pystray.Icon(
        f"apptray_{app['abbrev']}",
        icon_img,
        app["name"],
        menu)

    return icon

def main():
    cfg = load_config()
    apps = cfg["apps"]

    # Verify paths exist, fall back for common apps
    for app in apps:
        p = app["path"]
        if p.lower() == "explorer.exe":
            continue  # always works
        if not os.path.exists(p):
            # Try common alternative paths
            alts = [
                p.replace("Program Files", "Program Files (x86)"),
                p.replace("Program Files (x86)", "Program Files"),
                os.path.join(os.environ.get("LOCALAPPDATA",""), *p.split("\\")[-3:]),
            ]
            for alt in alts:
                if os.path.exists(alt):
                    app["path"] = alt
                    break

    # Launch each tray icon in its own thread
    threads = []
    icons = []
    for app in apps:
        icon = create_tray(app)
        icons.append(icon)
        t = threading.Thread(target=icon.run, daemon=True)
        t.start()
        threads.append(t)

    # Keep main thread alive
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        for icon in icons:
            icon.stop()

if __name__ == "__main__":
    import selfclean
    selfclean.ensure_single("app_tray.py")
    main()
