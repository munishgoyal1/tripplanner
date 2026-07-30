# Local dev cheat sheet

One page. Stick this on a second monitor.

---

## TL;DR - interactive testing

```powershell
.\scripts\dev\dev-spa.ps1
```

Open <http://localhost:5173> for the app or
<http://127.0.0.1:5175/catalog.html> for UX Labs in your regular browser
(Chrome / Edge / Firefox). Both frontend servers start automatically. The agent
can edit files and your chat session **will not** be wiped.

When you want to test the agent's latest code change:

1. Click into the terminal running `dev-spa.ps1`.
2. Press `Ctrl+C` to stop both processes.
3. Press Up then Enter to rerun `dev-spa.ps1`.
4. Switch to the **browser**, press `F5`.

That's it.

## Parallel coding windows

The default workflow opens two named VS Code workspaces:

- `tripplanner-worker-1.code-workspace` - Agent 1 Development on `agents/worker-1`
- `tripplanner-integration.code-workspace` - Agent 3 Review & Integration on `master`

Agent 2 on `agents/worker-2` remains available through
`Open-Tripplanner-All-Agents.cmd` when a third parallel assignment is worth the
coordination cost.

See [parallel-agent-development.md](parallel-agent-development.md) for worker
assignment, PR, synchronization, and merge rules.

To merge Agent 1 and restart this local stack in one click, double-click
`scripts/dev/Run-Latest-Code.cmd` from the repository root or run the VS Code task
**Tripplanner: Run Latest Code** from the integration workspace. Existing staged,
unstaged, and untracked master work is temporarily preserved and restored around
the guarded Worker 1 merge before the server starts. A Worker synchronization
conflict is automatically aborted so it cannot leave staged or unmerged residue.

---

## Why `dev-spa.ps1`?

It is the canonical local entrypoint for the current React SPA and FastAPI
backend. Hot reload is off by default, so backend edits do not interrupt an
in-progress chat. Pass `-Watch` only when you intentionally want reloads.

## Modes at a glance

| Script | Use when | Hot reload |
|---|---|---|
| `.\scripts\dev\dev-spa.ps1` | Local emulator, backend, SPA, and UX Labs | Off |
| `.\scripts\dev\dev-spa.ps1 -Watch` | Active code editing | On |
| `.\scripts\dev\dev-spa.ps1 -BackendOnly` | API only | Off |
| `.\scripts\dev\dev-spa.ps1 -FrontendOnly` | SPA and UX Labs only | Off |
| `.\scripts\dev\dev-spa.ps1 -NoLabs` | Regular stack without UX Labs | Off |
| `.\scripts\dev\dev-spa.ps1 -CosmosBackend azure` | Isolated Azure local database | Off |
| `.\scripts\dev\dev-spa.ps1 -UseCanaryData` | Explicit canary-data troubleshooting | Off |

---

## Observability

Two completely separate log streams. Both are auto-wired from
`tripplanner.observability` and start with `setup_logging()` at the top of
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

Key structured events emitted from the FastAPI application:

| `event_kind` | Fields |
|---|---|
| `api_chat_request` / `api_chat_stream_request` | sanitized request size |
| `chat_operation` | `transport`, terminal `outcome`, `duration_ms`, optional exception class |
| `tool_call` | `tool`, `status`, `ms`, `cache_hit` |
| `usage_recorded` | model, token counts, estimated cost |
| `api_oauth_login` | `provider` (no email / no name) |

The production reliability objectives, low-volume interpretation, release
response, and copy-paste KQL live in
[operations-slos.md](../operations/operations-slos.md).

KQL example once the container is running on Azure:

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s startswith "tripplanner-app-"
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
  `~/.tripplanner/audit/<YYYY-MM-DD>.jsonl`.
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
| Cancel a long-running request      | browser            | Click the **Stop** button in the chat composer |
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
.\scripts\setup-dev-machine.ps1
```

This installs missing Windows prerequisites with `winget`, restores pinned
Python and frontend dependencies, preserves an existing `.env`, and verifies a
frontend production build. Add `-IncludeMobile` for Expo dependencies. Account
login and provider secrets remain manual.

After that, every session is just `.\scripts\dev\dev-spa.ps1`.

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
| Local *(default)* | `~\.tripplanner\users\<id>\preferences.json` | `~\.tripplanner\users\<id>\active_trip.json` | `~\.tripplanner\users\<id>\trips\` |
| Azure local *(explicit)* | Cosmos `users` container | Cosmos `users/active_trip` doc | Cosmos `trips` container |

Delete the local files to start fresh; the server will recreate them on the
next save.

---

## Other useful commands

```powershell
# CLI mode (no browser)
.\.venv\Scripts\python.exe -m tripplanner.cli

# FastAPI mode (curl-friendly, no browser UI)
.\.venv\Scripts\python.exe -m tripplanner.api

# Tail user's persisted prefs as JSON
Get-Content "$env:USERPROFILE\.tripplanner\users\guest-*\preferences.json" | ConvertFrom-Json
```
