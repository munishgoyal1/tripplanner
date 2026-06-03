# Local dev cheat sheet

One page. Stick this on a second monitor.

---

## TL;DR — interactive testing

```powershell
.\scripts\test.ps1
```

Open <http://localhost:8000> in your **regular browser** (Chrome / Edge / Firefox).
Chat away. The agent can edit files and your chat session **will not** be wiped.

When you want to test the agent's latest code change:

1. Click into the **terminal** running `test.ps1`.
2. Press `Ctrl+C` → server stops.
3. Press `↑` then `Enter` → reruns `test.ps1`.
4. Switch to the **browser**, press `F5`.

That's it.

---

## Why `test.ps1` and not `dev.ps1`?

`test.ps1` is a wrapper that pre-applies the three flags you always want during
agent-driven testing:

| Flag | What it does | Why |
|---|---|---|
| `-NoBrowser` | Don't auto-open VS Code's integrated browser | Agent must not see your chat |
| `-WithAuth`  | Enable OAuth + guest cookie | Real identity for testing |
| `-NoWatch`   | **Disable hot reload on `.py` edits** | Keeps your chat alive while agent edits |

Without `-NoWatch`, every Python file the agent saves kills the server, drops
the WebSocket, and reloads the browser — wiping the in-progress chat.

---

## Scripts at a glance

| Script | Use when | Hot reload |
|---|---|---|
| `.\scripts\test.ps1`             | Munish testing while agent edits           | **OFF** (manual rerun) |
| `.\scripts\dev.ps1 -NoBrowser`   | Munish editing, no auth needed             | ON (~3s reload) |
| `.\scripts\dev.ps1 -NoBrowser -WithAuth`           | Munish editing, need OAuth         | ON  |
| `.\scripts\dev.ps1 -NoBrowser -WithAuth -NoWatch`  | Same as `test.ps1` (long form)     | OFF |
| `.\scripts\test.ps1 -Cosmos`     | Test against **prod Cosmos data** (careful) | OFF |
| `.\scripts\test.ps1 -Port 8080`  | Different port                              | OFF |
| `.\scripts\test.ps1 -Watch`      | Re-enable hot reload (only if YOU edit)     | ON  |
| `.\scripts\test.ps1 -OpenBrowser`| Auto-open VS Code's built-in browser        | OFF |

---

## Keyboard cheat sheet

| When you want to... | Where | Keys |
|---|---|---|
| Stop the dev server                | dev-server terminal | `Ctrl+C` |
| Restart the dev server             | dev-server terminal | `↑` then `Enter` |
| Refresh page (use new backend code) | browser tab        | `F5` *(or `Ctrl+R`)* |
| Force-drop browser cache too       | browser tab         | `Ctrl+Shift+R` *(only if F5 shows stale UI)* |
| Cancel a long-running request      | browser            | Click the **Stop** button in Chainlit composer |
| Copy text from terminal            | terminal           | Mouse-select, then `Enter` *(not Ctrl+C — that kills the server!)* |

> **`Ctrl+C` is for the TERMINAL.** In the browser it just copies selected text.

---

## How the agent debugs without screenshots

The dev-server terminal captures every Python stack trace. The agent reads it
directly from the terminal output, so you usually **don't** need to screenshot
errors. Just tell the agent "saving failed" or "got an error on /profile" and
it will pull the trace from the terminal.

You only need screenshots for:

- Visual / CSS issues (something looks wrong, not broken)
- Pointing at one specific message in a long chat
- Anything the agent can't infer from the trace

---

## First-time setup

```powershell
# 1. Install Python deps once
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,web]"

# 2. Configure .env (copy from .env.example and fill in keys)
Copy-Item .env.example .env
notepad .env

# 3. (Optional, only if testing OAuth) See docs/setup-oauth.md
```

After that, every session is just `.\scripts\test.ps1`.

---

## Run unit tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Should print `106 passed` (or higher) in ~1.5 seconds.

---

## Where data lives

| Mode | Preferences | Active trip | Archived trips |
|---|---|---|---|
| Local *(default)* | `~\.multiagent\users\<id>\preferences.json` | `~\.multiagent\users\<id>\active_trip.json` | `~\.multiagent\users\<id>\trips\` |
| `-Cosmos` *(prod)* | Cosmos `users` container | Cosmos `users/active_trip` doc | Cosmos `trips` container |

Delete the local files to start fresh; the server will recreate them on the
next save.

---

## Other useful commands

```powershell
# CLI mode (no browser, no Chainlit)
.\.venv\Scripts\python.exe -m multiagent.cli

# FastAPI mode (curl-friendly, no browser UI)
.\.venv\Scripts\python.exe -m multiagent.api

# Tail user's persisted prefs as JSON
Get-Content "$env:USERPROFILE\.multiagent\users\guest-*\preferences.json" | ConvertFrom-Json
```
