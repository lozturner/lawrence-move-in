# :pause_button: Mouse Pause

> Stop moving your mouse and an action panel appears.

**File:** [`mouse_pause.py`](../../mouse_pause.py)
**Version:** 1.0.0
**Tray Icon:** MP

---

## The Problem

Launching apps and tools requires navigating menus, finding shortcuts, or clicking through the Start menu. Every time you pause to think, your hands leave the keyboard and your mouse just sits there doing nothing. That idle moment is wasted.

## The Solution

A dwell-activated action panel. Stop moving your mouse for a configurable time (2-30 seconds) and a panel of 12+ action tiles appears. Click one to launch it. Lock mode means the panel stays until you dismiss it. Add your own custom actions. Even includes an AI input box for quick questions.

## Features

- :hourglass_flowing_sand: Configurable dwell timer (2-30 seconds)
- :jigsaw: 12+ action tiles in the panel
- :lock: Click to lock — mouse movement won't dismiss
- :heavy_plus_sign: Add custom actions (your own apps and scripts)
- :robot: AI input box for quick questions
- :snowflake: Configurable cooldown between activations
- :pushpin: Permanent show mode option

## How It Works

Tracks mouse position. When the cursor hasn't moved for the configured dwell time, an action panel appears near the cursor. Built with **tkinter**. Lock mode disables the dismiss-on-move behaviour. The AI input box sends questions to the **Claude API**. Custom actions are stored in config.

## Configuration

Edit `mouse_pause_config.json`:

```json
{
  "dwell_time_seconds": 5,
  "cooldown_seconds": 3,
  "permanent_show": false,
  "custom_actions": [
    {"name": "Notepad", "command": "notepad.exe"},
    {"name": "Calculator", "command": "calc.exe"}
  ]
}
```

## Usage

Launch `mouse_pause.py`. Stop moving your mouse for the configured dwell time. The action panel appears. Click a tile to launch that action. Click the lock icon to keep the panel open. Use the AI box to ask quick questions. Tray icon **MP** provides settings, pause, and quit.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
