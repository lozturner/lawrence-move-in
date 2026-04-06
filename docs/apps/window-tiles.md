# :window: Window Tiles

> Every open window as a coloured tile on a desktop canvas.

**File:** [`tiles.py`](../../tiles.py)
**Version:** 2.0.0
**Tray Icon:** TI

---

## The Problem

Alt-Tab is a flat list. The taskbar is a row of tiny icons. Neither gives you a spatial overview of what's actually open. When you've got 20+ windows across browsers, editors, and chat apps, finding the right one is a guessing game.

## The Solution

A desktop overlay that renders every open window as a coloured tile, grouped by category. Browser windows are one colour, editors another, chat apps another. Ghost mode drops the overlay to 10% opacity with click-through so it doesn't interfere with your work.

## Features

- :art: Colour-coded tiles grouped by category (Browser, Editor, Chat, etc.)
- :ghost: Ghost mode — 10% opacity with full click-through
- :mag: Search bar to filter windows by name
- :file_folder: Collapsible groups for tidy organisation
- :desktop_computer: Full desktop canvas overlay
- :eyes: Visual overview of every running window at a glance

## How It Works

Enumerates all visible windows and categorises them by process name into groups (Browser, Editor, Chat, Media, etc.). Renders coloured tiles on a transparent desktop overlay using **tkinter**. Ghost mode sets window opacity to 10% and enables click-through via Windows extended styles.

## Configuration

No external config file. Categories are defined internally based on known process names.

## Usage

Launch `tiles.py`. The canvas overlay appears showing all open windows as tiles. Use the search bar to filter. Click a tile to switch to that window. Toggle ghost mode from the tray menu. Collapse or expand category groups as needed. Tray icon **TI** provides access to settings and quit.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
