"""
Lawrence: Move In — Auto-launcher v1.2.0
Kills any existing suite processes, then launches everything fresh.
Runs silently (pythonw) — drop a shortcut to this in your Startup folder.
"""
import subprocess
import sys
import os
import time

VERSION = "1.2.0"
script_dir = os.path.dirname(os.path.abspath(__file__))
python = sys.executable.replace("python.exe", "pythonw.exe")
my_pid = os.getpid()

SUITE_SCRIPTS = ["niggly.py", "tiles.py", "launcher.py", "_open_canvas.py", "hot_corner.py", "windowbranch.py", "launch_all.pyw"]


def kill_old_processes():
    """Kill any leftover suite processes before launching fresh."""
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            if proc.info["pid"] == my_pid:
                continue
            try:
                name = (proc.info.get("name") or "").lower()
                if "python" not in name:
                    continue
                cmdline = proc.info.get("cmdline") or []
                cmd_str = " ".join(str(c) for c in cmdline)
                for script in SUITE_SCRIPTS:
                    if script in cmd_str:
                        proc.terminate()
                        break
            except Exception:
                pass
    except ImportError:
        pass  # No psutil — skip cleanup, just launch


# Kill old instances first
kill_old_processes()
time.sleep(0.5)  # Brief pause for processes to die

# Launch all applets fresh
subprocess.Popen([python, os.path.join(script_dir, "niggly.py")],
                 creationflags=0x00000008)  # DETACHED_PROCESS
subprocess.Popen([python, os.path.join(script_dir, "tiles.py")],
                 creationflags=0x00000008)
subprocess.Popen([python, os.path.join(script_dir, "launcher.py")],
                 creationflags=0x00000008)
subprocess.Popen([python, os.path.join(script_dir, "hot_corner.py")],
                 creationflags=0x00000008)
subprocess.Popen([python, os.path.join(script_dir, "windowbranch.py")],
                 creationflags=0x00000008)
