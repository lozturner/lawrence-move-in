# :eye: Watcher

> Mouse goes idle for 3 seconds, takes a screenshot, asks Claude what you're doing.

**File:** [`watcher.py`](../../watcher.py)
**Version:** 2.0.0
**Tray Icon:** WA

---

## The Problem

You lose track of what you were doing. You get distracted, context-switch, and ten minutes later you're staring at a screen with no idea what the task was. There's no ambient awareness layer that actually understands what's on your screen.

## The Solution

Watcher monitors your mouse. When it goes idle for 3 seconds, it takes a screenshot and sends it to Claude's Vision API for analysis. Claude makes a deduction about what you're working on and reads it aloud. A chat interface lets you give thumbs up/down feedback to improve accuracy.

## Features

- :camera: Auto-screenshot on 3-second mouse idle
- :brain: Claude Vision API analyses screen content
- :loud_sound: Voice readout of deductions via pyttsx3
- :thumbsup: Thumbs up/down feedback in chat interface
- :page_facing_up: Export conversation logs
- :key: API key stored in config

## How It Works

Monitors mouse position. After 3 seconds of no movement, captures a screenshot and sends it to the **Claude Vision API** for analysis. The response is displayed in a chat-style interface and read aloud using **pyttsx3** text-to-speech. Feedback (thumbs up/down) is logged for context.

## Configuration

Edit `kidlin_config.json`:

```json
{
  "api_key": "sk-ant-...",
  "idle_threshold": 3,
  "voice_enabled": true
}
```

## Usage

Launch `watcher.py`. It runs silently in the background. Stop moving your mouse for 3 seconds and it captures + analyses your screen. The chat interface shows deductions. Use thumbs up/down to give feedback. Export logs from the menu. Tray icon **WA** provides access to settings, pause, and quit.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
