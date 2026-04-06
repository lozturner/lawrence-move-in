# Lawrence: Move In — If-Then-That Behaviour Map

Mermaid flowcharts documenting the trigger → condition → action chain for each applet.
Used as architectural context for the suite.

---

## hub.py — Master Hub

```mermaid
flowchart TD
    A([User clicks tile]) --> B{Triple-click\nwithin 600ms?}
    B -- Yes --> C[Kill process\nthen relaunch after 300ms]
    B -- No --> D[Launch script\nvia pythonw detached]
    E([Right-click tile]) --> F[Context menu:\nMove Up / Move Down\nKill / Hard Reset]
    F --> G{Order changed?}
    G -- Yes --> H[Save to hub_config.json\nRebuild grid]
    I([LAUNCH ALL]) --> J[Spawn launch_all.pyw]
    K([3 s poll]) --> L[psutil scan all procs]
    L --> M{Script name\nin cmdline?}
    M -- Yes --> N[Dot = green ●]
    M -- No --> O[Dot = dim ○]
```

---

## niggly.py — Focus Rules (IFTTT Core)

```mermaid
flowchart TD
    A([Poll every 150ms]) --> B[GetForegroundWindow]
    B --> C{Window changed?}
    C -- No --> A
    C -- Yes --> D[Identify EXE + title]
    D --> E{Rule exists for\nthis window?}
    E -- No --> A
    E -- Yes --> F[Load paired hide-list]
    F --> G{Each paired window\nstill visible?}
    G -- Yes --> H[ShowWindow SW_MINIMIZE]
    H --> G
    G -- No --> A

    I([User drags window\nonto rule card]) --> J[Add to hide-list\nfor that trigger]
    J --> K[Save niggly_config.json]

    L([Toggle rule enabled]) --> M[Update config\nSkip on next poll]
```

---

## tiles.py — Window Tiles

```mermaid
flowchart TD
    A([Poll visible windows]) --> B[EnumWindows\nfilter by size + title]
    B --> C{New window\ndetected?}
    C -- Yes --> D[Assign accent colour\nby category]
    D --> E[Render tile with\nPIL icon + label]
    E --> F[Add to canvas grid]
    C -- No --> G{Window closed?}
    G -- Yes --> H[Remove tile\nfrom canvas]
    G -- No --> A

    I([Ghost mode toggle]) --> J{Alpha = 10%?}
    J -- Yes --> K[Passthrough clicks\nto desktop below]
    J -- No --> L[Normal interactive\noverlay]

    M([Click tile]) --> N[SetForegroundWindow\nto that HWND]
```

---

## watcher.py — Idle Watcher

```mermaid
flowchart TD
    A([Poll every 5s]) --> B[GetLastInputInfo]
    B --> C{Idle duration\n≥ threshold?}
    C -- No --> A
    C -- Yes --> D[Capture screen\nvia PIL ImageGrab]
    D --> E[Encode to base64]
    E --> F[POST to Claude Vision API\nwith prompt]
    F --> G[Parse response:\nwhat are you doing?]
    G --> H[Show floating\nnotification bubble]
    H --> I{User dismisses?}
    I -- Yes --> J[Reset idle timer]
    J --> A
    I -- No\ntimeout --> A
```

---

## voicesort.py — Voice Sort

```mermaid
flowchart TD
    A([Global hook:\nCtrl+C pressed]) --> B[Read clipboard text]
    B --> C{Text present?}
    C -- No --> A
    C -- Yes --> D[Send to Claude API\nwith category prompt]
    D --> E{Category returned}
    E --> F[thought / task / idea /\nrant / note / instruction\n/ observation / etc.]
    F --> G[Append to\nvoice_sorted/<category>.md]
    G --> H[Flash tray icon\nbriefly]
    H --> A

    I([Manual voice input\nScribe hotkey]) --> J[Vosk STT\ntranscribe audio]
    J --> D
```

---

## kidlin.py — Kidlin's Law

```mermaid
flowchart TD
    A([User types messy\nproblem in textbox]) --> B[Submit]
    B --> C[Send to Claude API:\n"Clarify what the actual problem is"]
    C --> D{API response}
    D --> E[Display clarified\nproblem statement]
    E --> F{User action}
    F -- Copy --> G[Clipboard copy]
    F -- Clear --> A
    F -- Save --> H[Append to\nkidlin_log.md]
```

---

## scribe.py — Floating Scribe

```mermaid
flowchart TD
    A([Hotkey / click record]) --> B[Open mic stream\nvia sounddevice]
    B --> C[Feed chunks to\nVosk recogniser]
    C --> D{Silence detected\nor stopped?}
    D -- No --> C
    D -- Yes --> E[Finalise transcript text]
    E --> F[Tag by content:\ntask / idea / note / etc.]
    F --> G[Display in\nfloating overlay]
    G --> H{User action}
    H -- Send to VoiceSort --> I[Append to category MD]
    H -- Copy --> J[Clipboard]
    H -- Dismiss --> A
```

---

## hot_corner.py — Hot Corners

```mermaid
flowchart TD
    A([Poll every 30ms]) --> B[GetCursorPos]
    B --> C{Cursor within\nsensitivity_px of corner?}
    C -- No --> D[Reset dwell timer\nfor that corner]
    D --> A
    C -- Yes --> E{Dwell ≥ dwell_ms\nAND cooldown elapsed?}
    E -- No --> A
    E -- Yes --> F[Read corner config:\naction name]
    F --> G{Action?}
    G -- task_view --> H[SendInput: Win+Tab]
    G -- alt_tab --> I[SendInput: Alt+Tab]
    G -- telegram_chat --> J[os.startfile\ntg://openmessage?chat_id=...]
    H & I & J --> K[Reset dwell timer\nSet last_trigger = now]
    K --> A
```

---

## annoyances.py — Annoyance Log

```mermaid
flowchart TD
    A([User types annoyance\nor pastes text]) --> B[Add to in-memory list]
    B --> C[Assign timestamp + ID]
    C --> D[Render as card\nin scrollable list]
    D --> E[Save to annoyances_data.json]
    E --> F[Export: append to\nDesktop/annoyances.md]

    G([Toggle resolved]) --> H{Checked?}
    H -- Yes --> I[Strike-through style\nMark resolved in JSON]
    H -- No --> J[Restore to active]

    K([Claude button]) --> L[Send annoyance text\nto Claude API]
    L --> M[Return workaround\nor fix suggestion]
    M --> N[Display in card\nbelow annoyance]
```

---

## Full Suite — If-Then-That Summary

```mermaid
flowchart LR
    subgraph Triggers
        T1[Window Focus]
        T2[Mouse Idle]
        T3[Ctrl+C / Clipboard]
        T4[Mic Audio]
        T5[Cursor in Corner]
        T6[Tile Click]
        T7[Text Submission]
        T8[Manual Entry]
    end

    subgraph Processing
        P1[win32gui poll]
        P2[PIL screenshot]
        P3[Claude API]
        P4[Vosk STT]
        P5[GetCursorPos]
        P6[psutil scan]
    end

    subgraph Outcomes
        O1[Windows hidden]
        O2[AI insight shown]
        O3[MD file updated]
        O4[Transcript tagged]
        O5[App launched]
        O6[Problem clarified]
        O7[Shortcut fired]
    end

    T1 --> P1 --> O1
    T2 --> P2 --> P3 --> O2
    T3 --> P3 --> O3
    T4 --> P4 --> O4
    T5 --> P5 --> O7
    T6 --> P6 --> O5
    T7 --> P3 --> O6
    T8 --> P3 --> O3
```
