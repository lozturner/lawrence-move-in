"""
Lawrence: Move In — Self-Clean Module
Import this at the top of any applet. It kills any older instance
of the same script on startup. Zero user action needed.

Usage in any applet:
    import selfclean
    selfclean.ensure_single("niggly.py")

Also available:
    selfclean.kill_only("mouse_pause.py")   # kill without being that script
    selfclean.kill_and_relaunch("mouse_pause.py")  # kill old, start fresh
"""

import os
import sys
import subprocess
from pathlib import Path

MY_PID = os.getpid()
SCRIPT_DIR = Path(__file__).resolve().parent
PYTHONW = Path(sys.executable).with_name("pythonw.exe")


def ensure_single(script_name: str):
    """Kill any other python process running this script. Call once at startup."""
    try:
        import psutil
    except ImportError:
        return

    killed = 0
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
                proc.kill()  # kill not terminate — force it
                killed += 1
        except Exception:
            pass

    if killed:
        import time
        time.sleep(0.3)  # give OS time to release resources


def kill_only(script_name: str):
    """Kill all instances of a script. Does NOT start a new one. Safe to call from any process."""
    try:
        import psutil
    except ImportError:
        return 0

    killed = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if proc.info["pid"] == MY_PID:
            continue
        try:
            name = (proc.info.get("name") or "").lower()
            if "python" not in name:
                continue
            cmdline = proc.info.get("cmdline") or []
            # Match by exact script filename in the cmdline
            for arg in cmdline:
                if arg.endswith(script_name) or arg.endswith(script_name.replace("/", "\\")):
                    proc.kill()
                    killed += 1
                    break
        except Exception:
            pass

    if killed:
        import time
        time.sleep(0.3)
    return killed


def kill_and_relaunch(script_name: str):
    """Kill all old instances of a script then launch a fresh one."""
    killed = kill_only(script_name)

    script_path = SCRIPT_DIR / script_name
    if script_path.exists():
        subprocess.Popen(
            [str(PYTHONW), str(script_path)],
            creationflags=0x00000008,
            cwd=str(SCRIPT_DIR))

    return killed


def is_already_running(script_name: str) -> bool:
    """Check if a script is already running (excluding current process).
    Use this before launching to prevent double instances."""
    try:
        import psutil
    except ImportError:
        return False

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        if proc.info["pid"] == MY_PID:
            continue
        try:
            name = (proc.info.get("name") or "").lower()
            if "python" not in name:
                continue
            cmdline = proc.info.get("cmdline") or []
            for arg in cmdline:
                if arg.endswith(script_name) or arg.endswith(script_name.replace("/", "\\")):
                    return True
        except Exception:
            pass
    return False


def safe_launch(script_name: str) -> bool:
    """Launch a script ONLY if it's not already running. Returns True if launched, False if skipped."""
    if is_already_running(script_name):
        return False  # already running, skip

    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        return False

    subprocess.Popen(
        [str(PYTHONW), str(script_path)],
        creationflags=0x00000008,
        cwd=str(SCRIPT_DIR))
    return True
