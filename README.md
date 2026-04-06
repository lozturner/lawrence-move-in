# Lawrence: Move In

**Portable software to overtake a Windows OS instead of suffering their flawed solutions.**

A suite of 15 Python applets that fix the things Windows gets wrong — window management, focus, voice input, AI assistance, session management, and more. Built by one developer with ADHD who got tired of fighting the OS.

---

## The Suite

| App | File | What it does |
|-----|------|-------------|
| **Hub** | `hub.py` | Steam Deck-style tile launcher. Green dot = running. Click = launch. Triple-click = hard reset. |
| **Focus Rules** | `niggly.py` | IF/THEN window pairing. "When I focus VS Code, minimise Slack." Polls every 150ms. |
| **Window Tiles** | `tiles.py` | Every open window as a coloured tile. Grouped by category. Ghost mode at 10% opacity with click-through. |
| **Master Launcher** | `launcher.py` | Gamification command centre. XP system. Glowing orbs. Level up by using your own tools. |
| **Watcher** | `watcher.py` | Mouse idle detection → screenshot → Claude Vision tells you what you're doing. Voice readout. |
| **Voice Sort** | `voicesort.py` | Catches Ctrl+C clipboard. AI categorises into thought/task/idea/rant and files to markdown. |
| **Kidlin's Law** | `kidlin.py` | Type messy thinking. Claude returns: "The actual problem is..." Clean problem statements. |
| **Scribe** | `scribe.py` | Floating speech-to-text via Vosk (offline). Auto-tags content. |
| **Annoyances** | `annoyances.py` | Persistent log of computer annoyances. AI suggests workarounds. Exports to markdown. |
| **Linker** | `linker.py` | Connector phrase tiles. Multi-select. Zoom. AI auto-suggest. Import/export JSON for free LLM reorganisation. |
| **Hot Corners** | `hot_corner.py` | Cursor hits screen corner → triggers action. Configurable per-corner. Run any file. |
| **Mouse Pause** | `mouse_pause.py` | Idle detection → action panel. Click to lock. Custom buttons. AI input box. Dwell timer. |
| **NACHO** | `nacho.py` | Voice AI assistant. Speaks to you, listens back. Every sentence is a hyperlink → email, Telegram, Claude, CodePen, Linker. |
| **Replay** | `replay.py` | Records screenshots, mouse trail, active windows, clipboard, processes. Scrub timeline. Export report. |
| **Winddown** | `winddown.py` | Session wind-down. Captures state, AI verification checklist, saves session, auto-resumes next launch. |

## Supporting Files

| File | Purpose |
|------|---------|
| `selfclean.py` | Auto-kills duplicate processes on startup |
| `kill_all.py` | Kills every running applet |
| `launch_all.pyw` | Starts everything silently |
| `make_shortcuts.py` | Generates Windows desktop shortcuts for every app |
| `hot_corner_config.json` | Per-corner action configuration |
| `linker_config.json` | Phrase categories, zoom, position |
| `mouse_pause_config.json` | Dwell timer, cooldown, custom actions |
| `replay_config.json` | Screenshot interval, quality, watched folders |

## Documentation

| File | What it is |
|------|-----------|
| `behavior.md` | Mermaid flowcharts: IF→THEN→THAT behaviour for every applet |
| `storyboard.html` | Single-page animated pitch: problem → solution for each app |
| `index.html` | Project documentation with architecture diagram |
| `index_presentation.html` | Full animated presentation with Three.js background |

## Requirements

```
Python 3.11+
pip install psutil pywin32 pystray pillow mss pyttsx3 sounddevice vosk anthropic
```

Vosk model (place in project root):
```
vosk-model-small-en-us-0.15/
```

Optional (for Watcher, Kidlin, Voice Sort, NACHO AI features):
- Anthropic API key in `kidlin_config.json`:
```json
{"api_key": "sk-ant-...", "model": "claude-sonnet-4-20250514"}
```

## Quick Start

```bash
# Generate desktop shortcuts (run once)
python make_shortcuts.py

# Launch everything
pythonw launch_all.pyw

# Or just the hub
pythonw hub.py
```

## Architecture

```
hub.py ─────┬── niggly.py      (focus rules)
            ├── tiles.py        (window tiles)
            ├── launcher.py     (gamification)
            ├── watcher.py      (idle → AI vision)
            ├── voicesort.py    (clipboard → AI sort)
            ├── kidlin.py       (problem clarifier)
            ├── scribe.py       (speech-to-text)
            ├── annoyances.py   (annoyance log)
            ├── linker.py       (phrase tiles)
            ├── hot_corner.py   (corner triggers)
            ├── mouse_pause.py  (idle action panel)
            ├── nacho.py        (voice AI assistant)
            ├── replay.py       (session recorder)
            └── winddown.py     (session wind-down)

All apps:
  • System tray icon
  • selfclean.py ensures single instance
  • Catppuccin Mocha dark theme
  • win32 APIs for window management
  • JSON config files (auto-created on first run)
```

## How the Loop Works

```
You start working
    → Hub launches your applets
    → Focus Rules manages your windows
    → Tiles shows what's open
    → Replay records everything

You pause (mouse idle)
    → Mouse Pause pops up with actions
    → NACHO talks to you
    → Watcher screenshots and deduces what you were doing

You think out loud
    → Scribe transcribes
    → Voice Sort categorises
    → Linker gives you connector phrases
    → Kidlin clarifies the problem

You want to stop
    → Winddown scans everything open
    → AI verifies you're actually done
    → Session saved

Next morning
    → Winddown detects last session
    → Offers to restore everything
    → You pick up where you left off
```

## License

Personal project by Loz Turner. Built with AI assistance.
