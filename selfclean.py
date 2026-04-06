"""
Lawrence: Move In — Self-Clean Module
Import this at the top of any applet. It kills any older instance
of the same script on startup. Zero user action needed.

Usage in any applet:
    import selfclean
    selfclean.ensure_single("niggly.py")
"""

import os
import sys

MY_PID = os.getpid()


def ensure_single(script_name: str):
    """Kill any other python process running this script. Call once at startup."""
    try:
        import psutil
    except ImportError:
        return  # can't check without psutil

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if proc.info["pid"] == MY_PID:
            continue
        try:
            name = (proc.info.get("name") or "").lower()
            if "python" not in name:
                continue
            cmdline = proc.info.get("cmdline") or []
            cmd_str = " ".join(str(c) for c in cmdline)
            if script_name in cmd_str:
                proc.terminate()
        except Exception:
            pass
