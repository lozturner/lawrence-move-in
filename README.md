<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/Applets-20-b4befe?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Lines-17%2C000+-a6e3a1?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Built%20With-Claude%20AI-cba6f7?style=for-the-badge" />
</p>

<h1 align="center">
  <br>
  Lawrence: Move In
  <br>
  <sub>Portable software to overtake a Windows OS instead of suffering their flawed solutions.</sub>
</h1>

<p align="center">
  <strong>20 Python applets</strong> that fix what Windows gets wrong.<br>
  Window management. Voice input. AI assistance. Session recording. Brain dumps.<br>
  Built by one developer with ADHD who got tired of fighting the OS.
</p>

---

## The Problem

It's 2026. AI sees everything. Yet Windows still can't:
- Focus a window without losing three others
- Tell you what you were doing 10 minutes ago
- Notice you've stopped working
- Help you finish what you started

**Lawrence: Move In** doesn't fix Windows. It replaces the bits that don't work.

---

## The Suite

> Every app below has its own documentation. Click the name to read the full story: **why it exists, what it does, how it works.**

### Window Management

| | App | File | What it solves |
|---|---|---|---|
| [docs](docs/apps/focus-rules.md) | **Focus Rules** | [`niggly.py`](niggly.py) | Focus one window, lose three others. IF/THEN rules: *"When I focus VS Code, minimise Slack."* |
| [docs](docs/apps/window-tiles.md) | **Window Tiles** | [`tiles.py`](tiles.py) | No visual map of what's open. Every window as a coloured tile. Ghost mode at 10% opacity. |
| [docs](docs/apps/hot-corners.md) | **Hot Corners** | [`hot_corner.py`](hot_corner.py) | No quick triggers. Cursor hits a screen corner, action fires. Run any file from any corner. |
| | **App Tray** | [`app_tray.py`](app_tray.py) | Your most-used apps have no permanent tray icons. Real icons extracted from .exe files. |

### AI & Voice

| | App | File | What it solves |
|---|---|---|---|
| [docs](docs/apps/nacho.md) | **NACHO** | [`nacho.py`](nacho.py) | No one to talk to when stuck. Voice AI that greets you, listens, responds. Every sentence is a hyperlink. |
| [docs](docs/apps/watcher.md) | **Watcher** | [`watcher.py`](watcher.py) | You zone out and forget. Mouse idle detection, screenshots desktop, Claude Vision tells you what you were doing. |
| [docs](docs/apps/kidlin.md) | **Kidlin's Law** | [`kidlin.py`](kidlin.py) | You can't articulate the problem. Type messy thinking, AI returns a clean problem statement. |
| [docs](docs/apps/voice-sort.md) | **Voice Sort** | [`voicesort.py`](voicesort.py) | Thoughts vanish the moment you think them. AI categorises every clipboard/voice note into markdown files. |
| [docs](docs/apps/scribe.md) | **Scribe** | [`scribe.py`](scribe.py) | You talk faster than you type. Floating offline speech-to-text via Vosk. Auto-tags content. |

### Productivity

| | App | File | What it solves |
|---|---|---|---|
| [docs](docs/apps/linker.md) | **Linker** | [`linker.py`](linker.py) | Can't find connector phrases. Tile board with multi-select, zoom, AI suggest, import/export for free LLMs. |
| [docs](docs/apps/capture.md) | **Capture** | [`capture.py`](capture.py) | Morning brain dump. Tray click, screenshot, chatbot popup, AI processes both, unique code, clipboard ready. |
| [docs](docs/apps/annoyances.md) | **Annoyances** | [`annoyances.py`](annoyances.py) | Computer annoyances pile up unfixed. Persistent log with AI workarounds. Exports to markdown. |
| [docs](docs/apps/launcher.md) | **Master Launcher** | [`launcher.py`](launcher.py) | No motivation to use your own tools. Gamification command centre. XP system. Glowing orbs. |
| | **Nag** | [`nag.py`](nag.py) | You forget what you should be doing. Timetable nagger linked to Google Calendar. |
| | **AI Timer** | [`aitimer.py`](aitimer.py) | 4 LLM chats open, lose track of time. Multiple concurrent timers. Check-in popups. Jump back. |

### Session Management

| | App | File | What it solves |
|---|---|---|---|
| [docs](docs/apps/mouse-pause.md) | **Mouse Pause** | [`mouse_pause.py`](mouse_pause.py) | You sit back with nothing to do. Idle detection, action panel, AI input, custom buttons. Click to lock. |
| [docs](docs/apps/replay.md) | **Replay** | [`replay.py`](replay.py) | You can't remember what you did an hour ago. Records everything. Scrub timeline. Mouse trail. Export report. |
| [docs](docs/apps/winddown.md) | **Winddown** | [`winddown.py`](winddown.py) | You don't know how to finish. State capture, AI verification checklist, session save, auto-resume next launch. |
| | **Steps Recorder** | [`steps.py`](steps.py) | Windows Steps Recorder is dead. Records every click, keystroke, window with screenshots and handles. |

### Infrastructure

| | App | File | Purpose |
|---|---|---|---|
| [docs](docs/apps/hub.md) | **Hub** | [`hub.py`](hub.py) | Steam Deck-style tile launcher. Green dot = running. Click = launch. Triple-click = hard reset. |
| | **Self-Clean** | [`selfclean.py`](selfclean.py) | Auto-kills duplicate processes on startup. Imported by every applet. |
| | **Kill All** | [`kill_all.py`](kill_all.py) | Emergency stop. Kills every running applet. |
| | **Launch All** | [`launch_all.pyw`](launch_all.pyw) | Starts the entire suite silently. |
| | **Gallery** | [`launch_gallery.py`](launch_gallery.py) | Level 4 visual gallery. Click-to-launch cards with thumbnails. Add external apps. |
| | **Level Launcher** | [`launch_level.py`](launch_level.py) | Tiered launcher: L1 essentials, L2 productivity, L3 full suite, L4 gallery. |
| | **Make Shortcuts** | [`make_shortcuts.py`](make_shortcuts.py) | Generates Windows desktop `.lnk` files for every app. |

---

## How the Loop Works

```
You start working
  Hub launches your applets
  Focus Rules manages your windows
  Tiles shows what's open
  Replay records everything

You pause (mouse idle)
  Mouse Pause pops up with actions
  NACHO talks to you
  Watcher screenshots and deduces what you were doing

You think out loud
  Scribe transcribes
  Voice Sort categorises
  Linker gives you connector phrases
  Kidlin clarifies the problem

You see something to capture
  Capture: screenshot + notes + AI = unique code on clipboard

You want to stop
  Winddown scans everything open
  AI verifies you're actually done
  Session saved

Next morning
  Winddown detects last session
  Offers to restore everything
  You pick up where you left off
```

---

## Architecture

```
hub.py
  niggly.py        Focus rules          win32gui polling
  tiles.py         Window tiles         win32gui + PIL canvas
  launcher.py      Gamification         tkinter + JSON state
  watcher.py       Idle detection       mss + Claude Vision API
  voicesort.py     Clipboard sorting    win32clipboard + Claude API
  kidlin.py        Problem clarifier    Claude API
  scribe.py        Speech-to-text       Vosk (offline) + sounddevice
  annoyances.py    Annoyance log        tkinter + Claude API
  linker.py        Phrase tiles         tkinter + PIL + Claude Vision
  hot_corner.py    Corner triggers      win32api cursor polling
  mouse_pause.py   Idle action panel    win32api + Claude API
  nacho.py         Voice AI             Vosk + pyttsx3 + Claude API
  replay.py        Session recorder     mss + psutil + win32gui
  winddown.py      Session wind-down    psutil + win32gui + Claude API
  capture.py       Brain dump           mss + Claude Vision API
```

**Shared across all apps:**
- System tray icon via `pystray`
- Single-instance via `selfclean.py`
- Catppuccin Mocha dark theme
- `win32` APIs for window management
- JSON config files (auto-created on first run)
- Claude API via shared `kidlin_config.json`

---

## Documentation

| File | What it is |
|---|---|
| [`docs/apps/`](docs/apps/) | Individual documentation for every applet |
| [`docs/diagrams.md`](docs/diagrams.md) | **8 architecture diagrams** — ERD, UML, sequence, flowchart, class, state, deployment, conversation flow |
| [`behavior.md`](behavior.md) | Mermaid flowcharts: IF/THEN/THAT for every applet |
| [`storyboard.html`](storyboard.html) | Single-page animated pitch: problem and solution for each app |
| [`index_presentation.html`](index_presentation.html) | Full animated presentation with Three.js particle background |
| [`docs/SKILL_session_audit.md`](docs/SKILL_session_audit.md) | Reusable session audit prompt — paste into any new chat |

---

## Quick Start

### Requirements

```bash
Python 3.11+
pip install psutil pywin32 pystray pillow mss pyttsx3 sounddevice vosk anthropic
```

### Vosk Model (offline speech-to-text)

Download and extract to the project root:
```
vosk-model-small-en-us-0.15/
```

### API Key (optional, for AI features)

Create `kidlin_config.json`:
```json
{
  "api_key": "sk-ant-...",
  "model": "claude-sonnet-4-20250514"
}
```

### Launch

```bash
# Generate desktop shortcuts (run once)
python make_shortcuts.py

# Launch everything
pythonw launch_all.pyw

# Or just the hub
pythonw hub.py
```

---

## Screenshots

> Open [`storyboard.html`](storyboard.html) in a browser for an animated walkthrough of every app.

---

<p align="center">
  <strong>Built by Loz Turner.</strong><br>
  Powered by Claude AI. Driven by ADHD.<br>
  One person's frustration. Twenty solutions.<br>
  <br>
  <sub>No committee. No spec. Just fix it.</sub>
</p>
