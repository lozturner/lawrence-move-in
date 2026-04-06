"""
Lawrence: Move In — Kill All Processes
Terminates every running instance of the suite's Python scripts.
Useful before launching fresh, or to clean up orphaned tray icons.
"""

import os
import sys
import signal

SUITE_SCRIPTS = [
    "niggly.py",
    "tiles.py",
    "launcher.py",
    "_open_canvas.py",
    "launch_all.pyw",
    "kill_all.py",  # don't kill ourselves until the end
]

MY_PID = os.getpid()


def kill_suite_processes():
    """Find and kill all python processes running suite scripts."""
    killed = []
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            if proc.info["pid"] == MY_PID:
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
                        killed.append((proc.info["pid"], script))
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        # Fallback: use tasklist + taskkill on Windows
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True
        )
        result2 = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq pythonw.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True
        )
        # Can't reliably filter by cmdline without psutil, so warn
        print("psutil not installed — using broad kill")
        print("This will kill ALL python/pythonw processes!")
        confirm = input("Continue? [y/N] ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return []

        for img in ["python.exe", "pythonw.exe"]:
            subprocess.run(["taskkill", "/F", "/IM", img],
                           capture_output=True)
        killed.append((0, "all python processes"))

    return killed


def main():
    print("=" * 50)
    print("  Lawrence: Move In — Kill All Processes")
    print("=" * 50)
    print()

    killed = kill_suite_processes()

    if killed:
        print(f"Terminated {len(killed)} process(es):")
        for pid, script in killed:
            print(f"  PID {pid:>6}  {script}")
    else:
        print("No suite processes found running.")

    print()
    print("Done. All clear for a fresh launch.")


if __name__ == "__main__":
    main()
