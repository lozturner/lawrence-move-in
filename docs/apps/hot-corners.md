# :diamond_shape_with_a_dot_inside: Hot Corners

> macOS-style hot corners with configurable actions for each screen corner.

**File:** [`hot_corner.py`](../../hot_corner.py)
**Version:** 2.0.0
**Tray Icon:** HC

---

## The Problem

Windows has no hot corners. macOS has had them for decades — shove your mouse into a corner and something useful happens. On Windows, those four corners are dead space. You're missing four instant-access shortcuts every time you reach for the edge of your screen.

## The Solution

Four screen corners, each with an independent configurable action. Adjustable sensitivity and dwell time so you don't trigger them accidentally. Actions range from Task View and Alt-Tab to launching specific apps, opening Telegram, or triggering other suite applets.

## Features

- :triangular_flag_on_post: 4 independent corner actions
- :wrench: Configurable sensitivity and dwell time
- :zap: Built-in actions: task_view, alt_tab, telegram_chat, mouse_pause, nacho, hub
- :open_file_folder: run_file action — browse and assign any file to a corner
- :gear: JSON config for all settings

## How It Works

Monitors mouse position at screen edges. When the cursor dwells in a corner for the configured duration, the assigned action fires. Uses **win32api** for cursor position and **keyboard/mouse simulation** for built-in actions. The `run_file` action uses a file browser dialog to assign any executable or file to a corner.

## Configuration

Edit `hot_corner_config.json`:

```json
{
  "corners": {
    "top_left": "task_view",
    "top_right": "alt_tab",
    "bottom_left": "telegram_chat",
    "bottom_right": "mouse_pause"
  },
  "sensitivity": 5,
  "dwell_time_ms": 300
}
```

## Usage

Launch `hot_corner.py`. Move your mouse into any screen corner and hold briefly. The configured action triggers. Right-click the tray icon **HC** to reassign corners, adjust sensitivity, or browse for a custom file to launch.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
