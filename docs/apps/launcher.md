# :crystal_ball: Master Launcher

> Gamification command centre with XP, levels, and glowing orbs.

**File:** [`launcher.py`](../../launcher.py)
**Version:** 1.0.0
**Tray Icon:** MI

---

## The Problem

Productivity tools are boring. You install them, use them for a week, then forget they exist. There's no feedback loop, no sense of progress, nothing that makes you want to keep using them.

## The Solution

A gamified command centre that awards XP for using the suite's tools. Glowing orbs represent each applet. Use them and you level up. It turns the mundane act of using your computer properly into something with momentum.

## Features

- :sparkles: Glowing orb interface for each applet
- :chart_with_upwards_trend: XP system that tracks tool usage
- :trophy: Level-up progression as you use more tools
- :joystick: Central command centre for the suite
- :gear: Configurable via JSON

## How It Works

Tracks interactions with the suite's applets and awards XP based on usage. The UI renders glowing orbs for each tool, with visual feedback as XP accumulates. Level thresholds are defined in config. Built with **tkinter** for the visual interface.

## Configuration

Edit `launcher_config.json`:

```json
{
  "xp_per_action": 10,
  "level_thresholds": [0, 100, 300, 600, 1000],
  "tracked_apps": ["hub", "niggly", "tiles", "watcher"]
}
```

## Usage

Launch `launcher.py`. The orb interface appears. Use any applet in the suite to earn XP. Watch your level grow. Tray icon **MI** provides quick access to stats and settings.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
