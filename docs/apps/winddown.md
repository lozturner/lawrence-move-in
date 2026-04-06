# :crescent_moon: Winddown

> End-of-session shutdown assistant that saves your state and restores it next time.

**File:** [`winddown.py`](../../winddown.py)
**Version:** 1.0.0
**Tray Icon:** WD

---

## The Problem

You close your laptop and lose everything. Open windows, clipboard contents, train of thought — gone. Next morning you spend 20 minutes reconstructing where you were. There's no graceful way to pause a session and resume it later.

## The Solution

Winddown scans your current state — open windows, clipboard, recent files, suite status — and generates a checklist. Add notes, verify with AI, and save the session. Next launch, it shows your last session and offers to relaunch applets, restore clipboard, and pick up where you left off.

## Features

- :mag: Scans open windows, clipboard, recent files, and suite status
- :white_check_mark: Auto-generated shutdown checklist
- :robot: AI verify button to check nothing is missed
- :memo: Notes field for context
- :floppy_disk: Saves full session state
- :arrows_counterclockwise: Resume flag — next launch restores previous session
- :rocket: Offers to relaunch applets and restore clipboard
- :page_facing_up: Markdown report export

## How It Works

Enumerates open windows via **win32gui**, reads clipboard contents, checks recent file access, and polls the suite's running status via **psutil**. Generates a checklist from this data. The AI verify button sends the checklist to **Claude** for a completeness check. Session state is serialised and saved. On next launch, the resume flag triggers restoration.

## Configuration

Session data is stored automatically. No manual config needed.

## Usage

Launch `winddown.py` when you're done for the day. Review the auto-generated checklist. Add notes about what you were working on. Click AI Verify to check nothing is missed. Save the session. Next time you start up, Winddown shows your last session and offers to restore everything. Tray icon **WD** provides quick access. Export a markdown report of any session.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
