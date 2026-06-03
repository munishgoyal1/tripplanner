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
| `.\scripts\test.ps1 -NoAutoHeal` | Skip the auto-heal watcher window           | OFF |

---

## Auto-heal watcher

`test.ps1` opens a **second pwsh window** running `scripts/autoheal.ps1`. It
tails the server log at `logs/server-<timestamp>.log` (also tee'd by
`dev.ps1`) and applies safe fixes when known issues appear.

| Pattern detected | What the healer does | Restart needed? |
|---|---|---|
| `ModuleNotFoundError: No module named '<X>'` | Prints the exact `pip install -e ".[dev,web]"` command | Yes (after you run it) |
| `json.decoder.JSONDecodeError` near user data | Moves the bad file to `*.corrupt.<stamp>`; app recreates defaults | No |
| `ImportError: bad magic number` etc. | Wipes `src/**/__pycache__/` so Python regenerates | Yes |
| `OSError: [Errno 10048]` (port in use) | Identifies the listener PID + prints exact `Stop-Process` command | No |
| `openai.NotFoundError` / `DeploymentNotFound` | Prints known-good API version + reminds you to check `AZURE_OPENAI_DEPLOYMENT` | Yes (after you fix .env) |
| `openai.AuthenticationError` / 401 | Lists the four env vars to recheck in `.env` | Yes |
| `openai.RateLimitError` / 429 | Detection only — prints "wait ~30s" advice | No |

Each healer has a per-healer cooldown (30–120s) so the same fix doesn't spam
on a repeating exception. Actions are logged to `logs/autoheal.log` with
timestamps.

**Safety**: package installs are never executed automatically — the watcher
prints the command and you copy-paste. Only fully reversible local actions
(file rename, cache delete) run by themselves.

**Disable per-run**: `.\scripts\test.ps1 -NoAutoHeal`
**Detection-only**: `.\scripts\test.ps1 -AutoHealDryRun` (logs what *would*
happen without changing anything — useful when you're tweaking the healer
rules in `scripts/autoheal.ps1`).

**Adding a new healer**: edit the `$Healers` array in
[`scripts/autoheal.ps1`](../scripts/autoheal.ps1). Each entry is `Name`,
`Pattern` (regex, multi-line, case-insensitive), `Cooldown` (seconds), and
`Action` (script block that takes the regex match). Keep actions safe and
reversible.

When you Ctrl+C the dev server, `test.ps1` auto-closes the watcher window.

---

## Observability

Two completely separate log streams. Both are auto-wired from
`multiagent.observability` and start with `setup_logging()` at the top of
each entrypoint (`web/app.py`, `api.py`, `cli.py`).

### Stream 1 — App log (sanitized, public-readable)

- **Local dev**: human-friendly text on stdout (`HH:MM:SS LEVEL logger: msg`).
- **Hosted (Container Apps)**: one-line JSON to stdout, auto-shipped to the
  Log Analytics workspace provisioned by `infra/main.bicep`.
- **What's sanitized before anything is written**:
  - Emails (`<email>`), phones (`<phone>`), IPv4s (`<ip>`), credit cards
    (`<card>`), Bearer tokens (`Bearer <token>`), `api_key=…` / `token=…` /
    `password=…` patterns (`<redacted>`).
  - `user_id` is replaced with a SHA-256 prefix `u_<12hex>` (stable for
    correlation, irreversible).
  - Reserved field names like `content`, `email`, `phone`, `name`,
    `display_name`, `query`, `text`, `message`, `destination`, `passport`,
    `dob`, etc. are dropped to `"<redacted>"` so the app log never carries
    the actual user message body or trip details.

Structured events emitted from `web/app.py`:

| `event_kind` | Fields |
|---|---|
| `session_start` | `is_guest`, `has_oauth` |
| `user_message` | `length`, `words` |
| `slash_command` | `length` |
| `tool_call` | `tool`, `status`, `ms` |
| `turn_complete` | `tool_calls`, `reply_length`, `ms` |
| `turn_error` | `error_kind`, `tool_calls`, `ms` |
| `oauth_login` | `provider` (no email / no name) |

KQL example once the container is running on Azure:

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s startswith "multiagent-app-"
| extend e = parse_json(Log_s)
| where tostring(e.event_kind) == "tool_call"
| summarize p95_ms = percentile(tolong(e.ms), 95), n = count()
        by tool = tostring(e.tool)
| order by n desc
```

### Stream 2 — Audit log (restricted, contains raw values)

For the rare cases where you need the actual user input (e.g. compliance
review, dataset curation), there's a separate sink that **never** touches
stdout:

- **Local dev**: appended as JSON Lines to
  `~/.multiagent/audit/<YYYY-MM-DD>.jsonl`.
- **Hosted**: written to the Cosmos DB container `audit_events` (partition
  key `/user_id`, `defaultTtl = 90 days` so PII auto-expires).

Events that go here:

| `kind` | Fields |
|---|---|
| `oauth_login` | `provider`, raw `name`, raw `email` |
| `user_message` | raw `content` — only when `AUDIT_USER_MESSAGES=1` |

`audit_event` writes are best-effort: if Cosmos is unreachable, the call
falls back to the local JSONL file and a single WARNING is emitted to the
app log. A failed audit write never blocks a user request.

Querying the audit container from the Azure Portal → Cosmos → `audit_events`
→ Items / Query:

```sql
SELECT TOP 50 c.ts, c.kind, c.content
FROM c
WHERE c.user_id = 'google-12345'
  AND c.kind = 'user_message'
ORDER BY c.ts DESC
```

### Env switches

| Var | Default | Effect |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Standard Python log level. |
| `LOG_JSON` | unset locally / `1` in Bicep | Emit JSON instead of text on stdout. |
| `AUDIT_USER_MESSAGES` | unset (off) | When `1`, persist raw message bodies to the audit sink. **Opt-in.** |

Bicep exposes `auditUserMessages` (default `false`) so the same opt-in is
visible at deploy time.

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
