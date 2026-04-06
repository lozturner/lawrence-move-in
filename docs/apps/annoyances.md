# :rage: Annoyances

> Persistent checklist of computer annoyances with AI-suggested workarounds.

**File:** [`annoyances.py`](../../annoyances.py)
**Version:** 1.0.0
**Tray Icon:** AN

---

## The Problem

Every computer has a list of things that annoy you. Small things — a font that renders wrong, a notification that won't stop, a default app that keeps resetting. You tolerate them because fixing each one individually feels like too much effort. They pile up until the whole experience feels broken.

## The Solution

A persistent checklist where you dump every annoyance as you encounter it. Claude suggests workarounds for each one. The list exports to markdown on your Desktop so you can track what's fixed and what's still irritating. No more tolerating death by a thousand paper cuts.

## Features

- :pencil: Quick text input to log annoyances as they happen
- :brain: Claude suggests workarounds for each item
- :white_check_mark: Checklist format — tick off what's resolved
- :page_facing_up: Exports to Desktop/annoyances.md
- :floppy_disk: Persistent storage between sessions

## How It Works

Stores annoyances in `annoyances_data.json` for persistence. When a new annoyance is added, it can be sent to the **Claude API** for a suggested workaround. The full list exports as a markdown file to the Desktop. UI is built with **tkinter**.

## Configuration

Data stored in `annoyances_data.json`:

```json
{
  "items": [
    {
      "text": "Windows keeps resetting default browser",
      "workaround": "Use SetUserFTA to lock file associations",
      "resolved": false
    }
  ]
}
```

## Usage

Launch `annoyances.py`. Type an annoyance into the input box and press enter. Click the AI button to get a suggested workaround. Tick items off when resolved. Export the list from the menu. Tray icon **AN** provides quick access.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
