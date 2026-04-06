# :movie_camera: Replay

> Records everything you do and lets you scrub through it like a video timeline.

**File:** [`replay.py`](../../replay.py)
**Version:** 1.0.0
**Tray Icon:** RP

---

## The Problem

You can't remember what you did 20 minutes ago. You had a tab open with something important, or you copied a URL that's now gone, or you were in a flow state and want to reconstruct what you did. There's no "undo" for your entire desktop session.

## The Solution

A full session recorder that captures screenshots, mouse position, active window, running processes, clipboard contents, and file changes. A built-in player lets you scrub through the timeline with a red mouse trail overlay showing where your cursor went. Export reports as markdown.

## Features

- :camera: Screenshots every 10 seconds
- :computer_mouse: Mouse position logged every 300ms
- :window: Active window tracked every 1 second
- :gear: Process list captured every 10 seconds
- :clipboard: Clipboard monitored every 2 seconds
- :file_folder: File changes tracked every 30 seconds
- :play_button: Timeline player with scrubber
- :triangular_ruler: Red mouse trail overlay with green cursor dot
- :fast_forward: Playback speed 0.5x to 4x
- :page_facing_up: Markdown report export

## How It Works

Runs multiple recording threads at different intervals: **PIL** for screenshots, **win32api** for mouse/window tracking, **psutil** for process snapshots, clipboard polling, and **watchdog** or polling for file changes. The player renders screenshots with a mouse trail overlay using **PIL** compositing. Timeline scrubber built in **tkinter**.

## Configuration

Edit `replay_config.json`:

```json
{
  "screenshot_interval": 10,
  "mouse_interval": 0.3,
  "window_interval": 1,
  "process_interval": 10,
  "clipboard_interval": 2,
  "file_change_interval": 30,
  "storage_path": "replay_data/"
}
```

## Usage

Launch `replay.py`. Recording starts automatically. Use the tray icon **RP** to open the player. Drag the timeline scrubber to browse your session. The red trail shows mouse movement, the green dot shows current position. Adjust playback speed. Export a markdown report of your session from the menu.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
