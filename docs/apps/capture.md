# :camera_with_flash: Capture

> Screenshot + chatbot popup for annotating and AI-analysing what's on screen.

**File:** [`capture.py`](../../capture.py)
**Version:** 1.0.0
**Tray Icon:** CP

---

## The Problem

Screenshots are dead images. You take one, it sits in a folder, and you forget why you took it. There's no way to annotate it in the moment, no AI analysis of what's in it, and no system for organising captures with context.

## The Solution

Left-click the tray icon to take a screenshot and immediately get a popup chatbot. Type notes about what you're capturing and why. Hit "Save & Process" and Claude Vision reads both the screenshot and your notes, generating a summary. Each capture gets a unique 8-character code for easy reference.

## Features

- :camera: Left-click tray icon for instant screenshot
- :speech_balloon: Popup chatbot for adding notes
- :brain: Claude Vision analyses screenshot + notes together
- :id: Unique 8-character code per capture
- :file_folder: Saves to captures/ folder
- :clipboard: Full record copied to clipboard
- :bell: Notification popup on save
- :open_file_folder: Browse all captures from tray menu

## How It Works

Left-clicking the tray icon triggers a screenshot via **PIL**. A chatbot popup appears for note entry. "Save & Process" sends the screenshot to the **Claude Vision API** along with the typed notes. Claude returns an analysis. The capture is saved to `captures/` with a unique 8-character ID. The full record (screenshot path, notes, AI analysis, code) is copied to clipboard.

## Configuration

Uses the shared API key from `kidlin_config.json`:

```json
{
  "api_key": "sk-ant-..."
}
```

## Usage

Left-click the tray icon **CP** to take a screenshot. A chatbot popup appears. Type any notes or context. Click "Save & Process" for AI analysis. The capture is saved with a unique code, and the full record is copied to your clipboard. Browse previous captures from the tray menu's browse option. A notification confirms each save.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
