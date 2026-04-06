# :card_file_box: Voice Sort

> Catches clipboard text, sends it to Claude, sorts it into categories.

**File:** [`voicesort.py`](../../voicesort.py)
**Version:** 1.0.0
**Tray Icon:** VS

---

## The Problem

You copy text constantly — thoughts, tasks, ideas, code snippets, rants — and it all vanishes into the clipboard void. There's no system for catching these fragments and filing them somewhere useful without manual effort.

## The Solution

Voice Sort intercepts Ctrl+C clipboard events, sends the copied text to Claude for categorisation, and files it into the appropriate markdown file. Thoughts go to thoughts.md, tasks to tasks.md, ideas to ideas.md, and so on. Zero-effort organisation.

## Features

- :clipboard: Catches Ctrl+C clipboard events automatically
- :brain: Claude API categorises content by type
- :file_folder: Files into voice_sorted/<category>.md
- :label: Categories: thought, task, idea, rant, observation, instruction, note, and more
- :zap: Runs silently in the background

## How It Works

Monitors the clipboard for changes triggered by Ctrl+C. When new text is detected, it sends the content to the **Claude API** with a categorisation prompt. Claude returns a category label, and the text is appended to the corresponding markdown file in the `voice_sorted/` directory.

## Configuration

Uses the shared API key from `kidlin_config.json`. No additional config needed.

```json
{
  "api_key": "sk-ant-..."
}
```

## Usage

Launch `voicesort.py`. It sits in the system tray as **VS**. Copy any text with Ctrl+C and it's automatically categorised and filed. Check `voice_sorted/` for your sorted content. Categories include: `thought.md`, `task.md`, `idea.md`, `rant.md`, `observation.md`, `instruction.md`, `note.md`, and others.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
