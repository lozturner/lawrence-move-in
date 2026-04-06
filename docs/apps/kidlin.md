# :bulb: Kidlin's Law

> Type messy thinking, get a clean problem statement back.

**File:** [`kidlin.py`](../../kidlin.py)
**Version:** 1.0.0
**Tray Icon:** KL

---

## The Problem

You know something's wrong but you can't articulate it. The problem is a fog in your head — half-formed frustrations and vague annoyances. You can't fix what you can't define, and you can't define it because your thinking is too messy.

## The Solution

Based on Kidlin's Law: "If you can write the problem down clearly, it's half solved." Type your messy, unstructured thinking into the box. Claude reads it and returns a clean, precise problem statement. The act of seeing your chaos reflected back as clarity is often enough to unlock the solution.

## Features

- :pencil2: Free-form text input for messy thoughts
- :brain: Claude API distils input into a clear problem statement
- :sparkles: Based on Kidlin's Law principle
- :zap: Instant turnaround — type and get clarity
- :key: API key via shared config

## How It Works

Takes raw text input from the user and sends it to the **Claude API** with a prompt designed to extract and reformulate the core problem. The response is a clean, structured problem statement displayed in the UI.

## Configuration

Edit `kidlin_config.json`:

```json
{
  "api_key": "sk-ant-..."
}
```

## Usage

Launch `kidlin.py`. A text input window appears. Type your messy thinking — stream of consciousness, half-sentences, whatever. Press enter or click submit. Claude returns a clear problem statement. Tray icon **KL** provides access to history and settings.

---

*Part of [Lawrence: Move In](../../README.md) — 16 applets that fix what Windows gets wrong.*
