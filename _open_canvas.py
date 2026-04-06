"""
Lawrence: Move In — Desktop Canvas Launcher v1.2.0
Tray icon shows "DC" in teal (distinct from the tiles "TL" blue icon).
Menu: Show Canvas, Refocus Canvas, Quit. Double-click shows canvas.
"""

__version__ = "1.2.0"

import os
import sys
import threading

sys.path.insert(0, r"C:/Users/123/Desktop/niggly_machine")

import pystray
from PIL import Image, ImageDraw, ImageFont
from tiles import DesktopCanvas


def create_canvas_tray_icon():
    """Create a 64x64 teal 'DC' icon for the canvas tray."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Teal background — distinct from tiles blue
    d.rounded_rectangle([2, 2, size - 2, size - 2], radius=12, fill=(148, 226, 213))
    try:
        f = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        f = ImageFont.load_default()
    d.text((size // 2, size // 2), "DC", fill=(15, 15, 26), font=f, anchor="mm")
    return img


def main():
    canvas = DesktopCanvas()

    def show_canvas(icon, item):
        threading.Thread(target=canvas.show, daemon=True).start()

    def refocus_canvas(icon, item):
        """Bring canvas back from passthrough ghost mode."""
        canvas.refocus()

    def quit_app(icon, item):
        if canvas.root:
            canvas._alive = False
            try:
                canvas.root.destroy()
            except Exception:
                pass
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Show Canvas", show_canvas, default=True),
        pystray.MenuItem("Refocus Canvas", refocus_canvas),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )

    icon = pystray.Icon("desktop_canvas", create_canvas_tray_icon(), f"Desktop Canvas v{__version__}", menu)
    # Auto-show canvas on launch
    threading.Timer(0.5, lambda: threading.Thread(target=canvas.show, daemon=True).start()).start()
    icon.run()


if __name__ == "__main__":
    import selfclean; selfclean.ensure_single("_open_canvas.py")
    main()
