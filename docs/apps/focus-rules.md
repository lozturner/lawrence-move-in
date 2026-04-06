# :dart: Focus Rules

> IF/THEN window pairing — when one app opens, another follows.

**File:** [`niggly.py`](../../niggly.py)
**Version:** 2.0.0
**Tray Icon:** NM

---

## The Problem

You open Figma and always need the brand guide beside it. You open VS Code and always want the terminal. Windows doesn't understand that certain apps belong together, so you waste time manually arranging windows every single session.

## The Solution

A rules engine that watches the foreground window and automatically brings paired windows forward. Define rules in plain language — "IF Figma is focused THEN show Brand Guide" — and Focus Rules handles the rest.

## Features

- :link: IF/THEN rules for automatic window pairing
- :speech_balloon: Natural language rule cards in the UI
- :zap: 150ms polling for near-instant response
- :gear: JSON config file for easy rule editing
- :eye: Monitors foreground window changes in real time

## How It Works

Polls the foreground window every 150ms using **win32gui**. When the active window matches a rule's trigger, it brings the paired window to the front. Rules are loaded from a JSON config and displayed as human-readable cards in the interface.

## Configuration

Edit `niggly_config.json`:

```json
{
  "rules": {
    "Figma": "Brand Guide",
    "VS Code": "Terminal",
    "Photoshop": "Reference Board"
  }
}
```

Each key is the trigger window title (or substring), and the value is the window to bring forward.

## Usage

Launch `niggly.py`. It runs in the background polling the active window. Add or edit rules through the UI cards or directly in `niggly_config.json`. The tray icon **NM** gives access to pause, edit rules, or quit.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
