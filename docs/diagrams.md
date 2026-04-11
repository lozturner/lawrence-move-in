# Lawrence: Move In — Architecture Diagrams

Full visual documentation of the 20-applet Body Double suite.
17,000+ lines of Python. One developer. Zero committees.

---

## 1. Entity Relationship Diagram (ERD)

How data flows between apps and their config/storage files.

```mermaid
erDiagram
    LAUNCHER ||--o{ APPLET : "launches"
    LAUNCHER {
        json launcher_config
        int xp
        int level
        int total_launches
    }
    APPLET {
        string script_name
        string version
        string tray_icon
        bool running
    }
    HUB ||--o{ APPLET : "displays tiles"
    GALLERY ||--o{ APPLET : "shows cards"
    GALLERY ||--o{ EXTERNAL_APP : "includes"
    EXTERNAL_APP {
        string path
        string name
        string category
        png thumbnail
    }
    GALLERY }o--|| EXTERNAL_CONFIG : "reads/writes"
    EXTERNAL_CONFIG {
        json external_apps_json
    }
    NIGGLY ||--|| NIGGLY_CONFIG : "persists rules"
    NIGGLY_CONFIG {
        json niggly_config_json
        array rules
    }
    TILES ||--|| TILES_CONFIG : "persists layout"
    TILES ||--|| CANVAS_CONFIG : "persists positions"
    TILES_CONFIG {
        json tiles_config_json
        dict groups
        bool locked
    }
    CANVAS_CONFIG {
        json canvas_config_json
        dict positions
        array zones
    }
    VOICESORT ||--o{ SORTED_FILE : "writes to"
    SORTED_FILE {
        md category_file
        string tag
    }
    VOICESORT }o--|| LEARNED_TAGS : "learns from"
    LEARNED_TAGS {
        json learned_tags_json
    }
    REPLAY ||--o{ SESSION : "records"
    SESSION {
        json session_json
        md report_md
        dir screenshots
    }
    CAPTURE ||--o{ CAPTURE_SESSION : "bundles"
    CAPTURE_SESSION {
        json compiled_json
        md compiled_md
        jpg screenshots
    }
    STEPS ||--o{ STEPS_SESSION : "captures"
    STEPS_SESSION {
        json session_json
        md report_md
        jpg step_screenshots
    }
    WINDDOWN ||--o{ WINDDOWN_SESSION : "saves state"
    WINDDOWN_SESSION {
        json state_json
        md report_md
    }
    NAG ||--|| TIMETABLE : "reads schedule"
    TIMETABLE {
        json nag_timetable_json
        array tasks
    }
    ANNOYANCES ||--|| ANNOYANCES_DB : "persists"
    ANNOYANCES_DB {
        json annoyances_data_json
        md annoyances_md
    }
    KIDLIN }o--|| API_KEY : "calls Claude"
    WATCHER }o--|| API_KEY : "calls Claude Vision"
    NACHO }o--|| API_KEY : "calls Claude"
    VOICESORT }o--|| API_KEY : "calls Claude"
    API_KEY {
        json kidlin_config_json
        string sk_ant_key
    }
    SCRIBE }o--|| VOSK_MODEL : "transcribes"
    NACHO }o--|| VOSK_MODEL : "listens"
    MOUSE_PAUSE }o--|| VOSK_MODEL : "hands-free"
    VOSK_MODEL {
        dir vosk_model_folder
        string language_model
    }
    AITIMER ||--o{ TIMER_LOG : "exports"
    TIMER_LOG {
        md timer_log_md
    }
    LINKER ||--|| LINKER_CONFIG : "persists phrases"
    LINKER_CONFIG {
        json linker_config_json
        array categories
        array phrases
    }
    HOT_CORNER ||--|| CORNER_CONFIG : "reads corners"
    CORNER_CONFIG {
        json hot_corner_config_json
        dict corners
    }
    APP_TRAY ||--|| TRAY_CONFIG : "reads apps"
    TRAY_CONFIG {
        json app_tray_config_json
        array apps
        ico icon_files
    }
    SELFCLEAN ||--o{ APPLET : "kills old versions"
```

---

## 2. UML Component Diagram

How the suite is structured into logical components.

```mermaid
graph TB
    subgraph Infrastructure
        SELFCLEAN[selfclean.py<br>Process manager]
        KILL_ALL[kill_all.py<br>Nuclear option]
        LAUNCH_ALL[launch_all.pyw<br>Silent auto-start]
        LAUNCH_LEVEL[launch_level.py<br>Tiered launcher L1-L4]
        MAKE_SHORTCUTS[make_shortcuts.py<br>Desktop shortcut generator]
    end

    subgraph Launchers
        LAUNCHER[launcher.py<br>XP + Gamification]
        HUB[hub.py<br>Steam Deck tiles]
        GALLERY[launch_gallery.py<br>Visual gallery + externals]
    end

    subgraph Window_Management["Window Management"]
        NIGGLY[niggly.py<br>IF/THEN focus rules]
        TILES[tiles.py<br>Tile sidebar + canvas]
        HOT_CORNER[hot_corner.py<br>Screen corner triggers]
        APP_TRAY[app_tray.py<br>Real icon tray]
    end

    subgraph AI_Voice["AI & Voice"]
        KIDLIN[kidlin.py<br>Kidlin's Law clarifier]
        WATCHER[watcher.py<br>Screenshot + Vision]
        NACHO[nacho.py<br>Voice AI assistant]
        SCRIBE[scribe.py<br>Floating STT]
        VOICESORT[voicesort.py<br>Clipboard categoriser]
        MOUSE_PAUSE[mouse_pause.py<br>Idle action panel]
    end

    subgraph Session_Mgmt["Session Management"]
        REPLAY[replay.py<br>Desktop recorder]
        CAPTURE[capture.py<br>Screenshot brain dump]
        STEPS[steps.py<br>Steps recorder]
        WINDDOWN[winddown.py<br>Session closer]
        ANNOYANCES[annoyances.py<br>Bug tracker]
        NAG[nag.py<br>Timetable nagger]
        AITIMER[aitimer.py<br>LLM time tracker]
    end

    subgraph Productivity
        LINKER[linker.py<br>Connector phrases]
    end

    LAUNCH_LEVEL --> SELFCLEAN
    LAUNCHER --> HUB
    HUB --> GALLERY
    GALLERY -->|launches| Window_Management
    GALLERY -->|launches| AI_Voice
    GALLERY -->|launches| Session_Mgmt
    GALLERY -->|launches| Productivity
    SELFCLEAN -->|kills old| Window_Management
    SELFCLEAN -->|kills old| AI_Voice
    SELFCLEAN -->|kills old| Session_Mgmt
```

---

## 3. Sequence Diagram — User Session Lifecycle

From boot to wind-down.

```mermaid
sequenceDiagram
    participant U as User
    participant L as Launch Level
    participant SC as selfclean
    participant Apps as Suite Apps
    participant MP as Mouse Pause
    participant NA as NACHO
    participant WD as Winddown

    U->>L: Double-click Level shortcut
    L->>SC: Kill old processes
    SC-->>L: Clean slate
    L->>Apps: Launch Level 1/2/3/4 apps
    Apps-->>U: Tray icons appear

    Note over U,Apps: User works normally

    U->>U: Stops moving mouse (8s)
    MP->>U: Action panel pops up
    U->>MP: Click "NACHO"
    MP->>NA: Launch voice assistant
    NA->>U: "Hi Loz, what are you up to?"
    U->>NA: Speaks (STT captures)
    NA->>U: Responds + hyperlinked text
    U->>NA: Clicks sentence → Email/Telegram/Save

    Note over U,Apps: User finishes work

    U->>WD: Open Winddown
    WD->>Apps: Scan all running apps
    WD->>U: Checklist: unsaved work? drafts? tabs?
    U->>WD: Tick items, add notes
    WD->>WD: Save session state
    WD-->>U: "See you tomorrow"

    Note over U,WD: Next day

    U->>WD: Launch Winddown
    WD->>U: "Welcome back" + yesterday's state
    U->>WD: Resume selected apps
    WD->>Apps: Relaunch from saved state
```

---

## 4. Flowchart — App Launch Decision Tree

```mermaid
flowchart TD
    START([User wants to use suite]) --> LEVEL{Which level?}

    LEVEL -->|L1 Essential| L1[Hot Corners + Focus Rules<br>+ Tiles + App Tray + Nag]
    LEVEL -->|L2 Productivity| L2[L1 + Hub + Linker<br>+ Mouse Pause + Scribe<br>+ Voice Sort + Kidlin + AI Timer]
    LEVEL -->|L3 Full Suite| L3[L2 + Watcher + NACHO<br>+ Replay + Capture + Winddown<br>+ Annoyances + Launcher + Steps]
    LEVEL -->|L4 Gallery| L4[Visual picker<br>Choose individual apps]

    L1 --> CHECK{selfclean:<br>already running?}
    L2 --> CHECK
    L3 --> CHECK
    L4 --> CHECK

    CHECK -->|Yes| SKIP[Skip launch]
    CHECK -->|No| LAUNCH[safe_launch via pythonw]
    LAUNCH --> TRAY[Tray icon appears]
    TRAY --> RUNNING([App running])
```

---

## 5. Class Diagram — Core Patterns

```mermaid
classDiagram
    class SelfClean {
        +ensure_single(script_name)
        +kill_only(script_name)
        +kill_and_relaunch(script_name)
        +is_already_running(script_name) bool
        +safe_launch(script_name) bool
    }

    class FocusMonitor {
        -_config_lock: Lock
        -_rules: list
        -_running: bool
        +start()
        +stop()
        +poll_foreground()
        +apply_rules()
    }

    class TilesWindow {
        -_snapshot: dict
        -_redrawing: bool
        -_icon_cache: OrderedDict
        +_redraw()
        +_check_and_redraw()
        +_force_redraw()
    }

    class DesktopCanvas {
        -_passthrough: bool
        -_tile_positions: dict
        -_zones: list
        +_enter_passthrough()
        +_exit_passthrough()
        +_draw_zone()
        +_populate()
        +_soft_refresh()
        +refocus()
    }

    class WindowTimer {
        +key: str
        +elapsed: float
        +running: bool
        +paused: bool
        +tick(dt)
        +pause()
        +resume()
        +stop()
        +needs_check() bool
    }

    class StepsRecorder {
        -_mouse_hook: HHOOK
        -_kb_hook: HHOOK
        -_typing_buffer: list
        +start_session()
        +stop_session()
        -_mouse_callback()
        -_kb_callback()
        -_flush_typing()
        -_save_session()
    }

    class GalleryLauncher {
        -_all_apps_cache: list
        -thumb_imgs: dict
        -_status_dot_canvas: dict
        +_make_card()
        +_launch_single()
        +_launch_all()
        +_rebuild_gallery()
        +_show_add_dialog()
        +_poll_running()
    }

    SelfClean <.. FocusMonitor : uses
    SelfClean <.. TilesWindow : uses
    SelfClean <.. GalleryLauncher : uses
    TilesWindow *-- DesktopCanvas : contains
    GalleryLauncher o-- WindowTimer : tracks
```

---

## 6. State Diagram — Mouse Pause Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Monitoring: App starts
    Monitoring --> PanelShown: Mouse idle > threshold
    PanelShown --> Locked: User clicks panel
    PanelShown --> Monitoring: Mouse moves
    Locked --> ActionTaken: User clicks a tile
    Locked --> Dismissed: User clicks X
    ActionTaken --> Monitoring: Action completes
    Dismissed --> Monitoring: Panel closes
    Monitoring --> Paused: User pauses via tray
    Paused --> Monitoring: User resumes via tray
    Monitoring --> Permanent: Toggle permanent ON
    Permanent --> PanelShown: Always visible
    PanelShown --> HandsFree: Voice module starts
    HandsFree --> WakeWord: Listening for "yes"
    WakeWord --> Recording: User says "yes"
    Recording --> WakeWord: 10s recording complete
    WakeWord --> EndSession: User clicks End
    EndSession --> Monitoring: Session compiled
```

---

## 7. Deployment Diagram — File Layout

```mermaid
graph LR
    subgraph Desktop["C:\\Users\\Desktop"]
        SHORTCUTS["22x .lnk shortcuts"]
        ANNOYANCES_MD[annoyances.md]
    end

    subgraph NigglyMachine["C:\\Users\\Desktop\\niggly_machine\\"]
        direction TB
        APPS_PY["20x .py applets"]
        SELFCLEAN_PY[selfclean.py]
        LAUNCH_LEVEL_PY[launch_level.py]

        subgraph Config["Config Files"]
            KIDLIN_CFG[kidlin_config.json<br>API key]
            NIGGLY_CFG[niggly_config.json]
            TILES_CFG[tiles_config.json]
            CANVAS_CFG[canvas_config.json]
            LINKER_CFG[linker_config.json]
            NAG_CFG[nag_timetable.json]
            HOT_CFG[hot_corner_config.json]
            TRAY_CFG[app_tray_config.json]
            EXT_CFG[external_apps.json]
            LAUNCHER_CFG[launcher_config.json]
        end

        subgraph Sessions["Session Data"]
            REPLAY_S[replay_sessions/]
            CAPTURE_S[capture_sessions/]
            STEPS_S[steps_sessions/]
            WINDDOWN_S[winddown_sessions/]
            AITIMER_L[aitimer_logs/]
            WATCHER_L[watcher_logs/]
            VOICESORT_D[voice_sorted/]
        end

        subgraph Assets["Assets"]
            THUMBS[thumbnails/<br>20x .png]
            ICONS[icons/<br>5x .ico]
            VOSK[vosk-model-small-en-us-0.15/]
        end

        subgraph Docs["Documentation"]
            README_MD[README.md]
            STORYBOARD[storyboard.html]
            PRESENTATION[index_presentation.html]
            BEHAVIOR[behavior.md]
            DIAGRAMS[docs/diagrams.md]
            SKILL[docs/SKILL_session_audit.md]
        end
    end

    subgraph GitHub["github.com/lozturner"]
        MAIN_REPO[lawrence-move-in]
        TRAY_REPO[windows-app-tray]
    end

    subgraph Startup["Windows Startup"]
        STARTUP_LNK[Niggly Machine.lnk]
    end

    SHORTCUTS --> NigglyMachine
    STARTUP_LNK --> LAUNCH_LEVEL_PY
    NigglyMachine --> MAIN_REPO
```

---

## 8. Conversation Flow — NACHO Voice Assistant

```mermaid
sequenceDiagram
    participant U as User (voice)
    participant V as Vosk STT
    participant N as NACHO
    participant C as Claude API
    participant T as Windows TTS

    N->>T: "Hi Loz, what are you up to?"
    T-->>U: Speaks greeting
    N->>V: Start listening (10s)
    U->>V: Speaks naturally
    V->>N: Transcribed text
    N->>N: Display user text (green, editable)
    N->>C: Send to Claude (max 150 tokens)
    C-->>N: Response text
    N->>N: Display as hyperlinked sentences
    N->>T: Speak response aloud
    T-->>U: Hears response

    Note over U,N: User comes back later, reads conversation

    U->>N: Hovers over a sentence
    N->>N: Underline + accent colour
    U->>N: Clicks sentence
    N->>N: Show action bar
    U->>N: Clicks Email / Telegram / Save / Claude
    N->>N: Execute action on that text
```

---

## Stats

| Metric | Value |
|--------|-------|
| Total applets | 20 |
| Lines of Python | 17,153 |
| Config files | 10 |
| Session data dirs | 7 |
| Desktop shortcuts | 22 |
| Mermaid diagrams | 8 |
| GitHub repos | 2 |
| Developer | 1 |
| Committees | 0 |
