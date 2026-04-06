# :control_knobs: Hub

> Steam Deck-style tile launcher for every applet in the suite.

**File:** [`hub.py`](../../hub.py)
**Version:** 1.0.0
**Tray Icon:** HB

---

## The Problem

You've got 16 applets running as separate processes with separate tray icons. Launching them individually is tedious, checking which ones are running means squinting at the system tray, and there's no central place to manage the lot.

## The Solution

A tile-based launcher inspired by the Steam Deck UI. Every applet gets a tile. Green dot means running. One click launches, triple-click hard resets. A single "Launch All" button spins up the entire suite.

## Features

- :green_circle: Live status indicators — green dot on running applets
- :computer_mouse: Click to launch, triple-click to hard reset a stuck process
- :rocket: "Launch All" button to start the entire suite in one go
- :right_click: Right-click context menu on each tile
- :floppy_disk: Remembers window position between sessions
- :jigsaw: Grid layout with labelled tiles for all 16 applets

## How It Works

Built with **tkinter** for the UI. Uses **psutil** to poll process status and detect which applets are alive. **pystray** handles the system tray icon. **PIL** renders the tray icon image. Launches applets as subprocesses and monitors their PIDs.

## Configuration

No separate config file. Hub discovers applets from its internal registry and persists window position automatically.

## Usage

Launch `hub.py` directly. The tile grid appears on screen. Left-click any tile to launch that applet. Triple-click a tile to force-kill and restart it. Right-click for additional options. Use the "Launch All" button to start everything. Hub sits in the system tray as **HB** when minimised.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
