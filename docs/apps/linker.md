# :chains: Linker

> Connector phrase tiles for building sentences from reusable fragments.

**File:** [`linker.py`](../../linker.py)
**Version:** 2.2.0
**Tray Icon:** LK

---

## The Problem

You type the same connecting phrases over and over — "as a result", "in addition to", "however", "for example". Writing fluent prose means reaching for these constantly, and the repetitive typing breaks your flow. Copy-pasting from old documents is clunky.

## The Solution

A tile-based phrase picker with 80+ connector phrases across 8 categories. Click a tile and it copies to clipboard. Multi-select mode lets you chain phrases together with configurable join characters. AI auto-suggest analyses your screen and recommends relevant phrases.

## Features

- :jigsaw: 80+ connector phrases across 8 categories
- :computer_mouse: Click any tile to copy to clipboard
- :link: Multi-select mode with join modes (space, comma, newline, arrow, pipe)
- :mag: Zoom 70%-200% for accessibility
- :pushpin: Pin favourite phrases to the top
- :robot: AI auto-suggest via screenshot analysis
- :arrow_down: Import/Export JSON for free LLM reorganisation
- :wastebasket: Clear clipboard button
- :smiley: Emoji icons on tiles

## How It Works

Renders phrase tiles in a scrollable grid using **tkinter**. Click copies to clipboard via **pyperclip**. Multi-select accumulates phrases and joins them with the selected separator. AI auto-suggest captures a screenshot and sends it to Claude to recommend contextually relevant phrases. Import/Export allows reorganising phrases with any LLM.

## Configuration

Phrases and layout can be exported/imported as JSON:

```json
{
  "categories": {
    "Addition": ["furthermore", "moreover", "in addition"],
    "Contrast": ["however", "nevertheless", "on the other hand"],
    "Cause": ["therefore", "consequently", "as a result"]
  },
  "favourites": ["however", "therefore", "for example"]
}
```

## Usage

Launch `linker.py`. Browse phrases by category. Click a tile to copy it. Hold Ctrl for multi-select, then choose a join mode. Use the zoom slider for comfortable reading. Pin frequent phrases. Use AI suggest for context-aware recommendations. Tray icon **LK** provides quick access.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
