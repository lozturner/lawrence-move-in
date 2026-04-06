---
name: session-audit
description: Audit the Lawrence Move In suite — what's running, what's broken, what needs doing
---

# Session Audit Skill

Run this at the start of any new chat to catch up on the state of the Lawrence: Move In suite.

## Prompt

```
Audit the Lawrence: Move In suite at C:\Users\123\Desktop\niggly_machine\

Do all of the following in parallel where possible:

1. LIST every .py and .pyw file in the directory
2. CHECK which apps are currently running (psutil, filter for niggly_machine in cmdline)
3. LIST all "Lawrence —" desktop shortcuts
4. READ the git log (last 15 commits)
5. CHECK which apps are in hub.py's TILES list
6. CHECK which apps are in mouse_pause.py's DEFAULT_ACTIONS list
7. CHECK which apps are in make_shortcuts.py's SHORTCUTS list
8. READ the README.md to see what's documented

Then produce a STATUS REPORT with:

### Running Now
Table: app name, PID, status

### Not Running (should be)
Table: app name, why it matters

### Missing From Hub
Apps that exist but aren't in the hub tile grid

### Missing Shortcuts
Apps without a desktop .lnk file

### Missing From make_shortcuts.py
Apps that won't get regenerated if shortcuts are remade

### Stale Documentation
- README mentions X apps, but Y exist
- behavior.md covers Z apps, but more exist
- docs/apps/ has N files, should have M

### Loose Ends
Anything that looks half-done, broken configs, orphan files, dead code

### Suggested Next Actions
Prioritised list of what to fix first

After the report, ask: "Want me to fix any of these?"
```

## When to use

- Start of a new chat session
- After a long coding session with lots of changes
- Before committing/pushing to GitHub
- When Loz says "catch me up" or "what's the state"
