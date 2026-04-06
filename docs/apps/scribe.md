# :microphone: Scribe

> Floating speech-to-text with offline recognition and auto-tagging.

**File:** [`scribe.py`](../../scribe.py)
**Version:** 1.0.0
**Tray Icon:** SC

---

## The Problem

You think faster than you type. Ideas come mid-task, mid-conversation, mid-walk. By the time you open a notes app and start typing, the thought is half gone. You need a way to capture speech instantly without leaving what you're doing.

## The Solution

A floating speech-to-text widget that uses offline recognition. No internet required, no API calls, no latency. Speak, and your words appear as text. Auto-tags the content and can send it directly to Voice Sort for categorisation or copy it to clipboard.

## Features

- :studio_microphone: Offline speech-to-text via Vosk
- :feather: Floating widget that stays on top
- :label: Auto-tags transcribed content
- :link: Send directly to Voice Sort for categorisation
- :clipboard: Copy transcription to clipboard
- :no_entry_sign: No internet connection required

## How It Works

Uses **Vosk** for offline speech-to-text recognition and **sounddevice** for microphone input. The floating widget captures audio, transcribes it in real time, and displays the text. Auto-tagging analyses the content type. Integration with Voice Sort passes text through for AI categorisation.

## Configuration

Requires Vosk model files to be present locally. No external API needed.

## Usage

Launch `scribe.py`. A floating widget appears. Click the microphone button or use the hotkey to start recording. Speak naturally. Text appears in real time. Use the toolbar to send to Voice Sort, copy to clipboard, or clear. Tray icon **SC** provides quick access and settings.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
