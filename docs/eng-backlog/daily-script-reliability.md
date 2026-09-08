# Daily Script Reliability and Friction

Status: Deferred  
Recorded: 2026-08-15  
Owner surface: `scripts/mac/user/`, `scripts/win/user/`, `scripts/dev/`, and shared script libraries

## Scope

This backlog captures recurring friction across the commands used for normal local
work: starting and synchronizing primary, creating and operating sandboxes, running
validation and corpus generation, and using debug-store and capture tools. Hosted
release scripts retain their separate approval and deployment requirements.

This is not approval to implement the work. Re-read current scripts and logs before
starting because individual symptoms may already have local fixes. The deeper sandbox
landing transaction is tracked in
[Sandbox Promotion Reliability](sandbox-promotion-reliability.md).

`Promote-Sandbox` retaining and resynchronizing the sandbox by default is intentional.
Passing `-Discard` selects retirement after landing. Do not treat that default as a
friction item.

## Desired Daily Command Contract

Every owner-facing command should:

1. Work from any current directory through its macOS or Windows launcher.
2. Resolve and print the exact repository, lane, interpreter, runtime, ports, and data
   target before mutation.
3. Run one complete preflight and report all actionable blockers together.
4. Avoid changing unrelated worktrees, processes, branches, data, or remote state.
5. Be idempotent or persist a resumable phase before an irreversible operation.
6. Distinguish expected waiting from errors and remote success from local follow-up.
7. End with exactly one outcome: completed, failed, interrupted, queued, or partial.
8. Print one exact recovery command for every expected failure.
9. Produce a useful last-run transcript containing native child output and exit codes.
10. Behave equivalently on supported Windows and macOS hosts.

## Observed Friction

### 1. Source-control state blocks unrelated operations

The primary checkout is treated as part of sandbox landing even when GitHub can merge
the remote sandbox branch independently. Both dirty and merely non-identical primary
state have repeatedly blocked promotion.

A representative failure from
`logs/last-run/sandbox-1-super-intelligence-merge.log` was:

```text
Primary checkout must match origin/master before promotion
(local 11769ad5913fd1ea4b3e7a5069d62abd3d582864,
 remote 5a83eab8e8ddb5eb804eae49ab51b453daf6f42f).
```

The message exposes two SHAs but does not say whether local is ahead, behind, or
diverged; whether remote state changed; why equality is required; or which recovery
command is safe. A local-ahead commit and an unrelated dirty file are both surfaced as
hard blockers rather than local follow-up states.

Revisit:

- Make remote-only operations independent of local-primary cleanliness.
- Classify ahead, behind, diverged, dirty, and stale remote-tracking state separately.
- List changed files for dirty-state failures and print a non-destructive recovery
  command appropriate to the classification.
- Never ask the owner to stash or commit without identifying whose work would move.
- Preserve partial success across batch sync or multi-sandbox operations.

### 2. Promotion and synchronization are not one resumable transaction

Merge, promote, update, Lab recording, primary refresh, registry writes, and optional
cleanup overlap but do not share a durable phase model. Similar workflows have drifted
in conflict recovery and post-merge handling. See the promotion-specific backlog for
the exact-SHA, locking, queue, registry, and retry requirements.

Revisit across all source-control scripts:

- Share fetch, state classification, conflict recovery, and final reporting helpers.
- Freeze inputs before validation and recheck them before mutation.
- Ensure `-WhatIf` and declined confirmation create no commits or file changes.
- Make every sync safe to retry after interruption or conflict resolution.
- Report per-lane success, failure, and pending recovery at the end of batch commands.

### 3. Runtime selection differs by command and worktree

Daily scripts resolve Python, Node, PowerShell, package installations, and source roots
through different paths. Retained sandbox logs show `ModuleNotFoundError: No module
named 'uvicorn'` before fallback. Historical promotion logs show Node 20
`ERR_REQUIRE_ESM` failures. A shared primary virtual environment can silently import
primary source unless a sandbox command sets `PYTHONPATH` correctly.

macOS launchers repair the PowerShell path, but detached child processes can start bare
`pwsh`. A VS Code process launched under Homebrew's sanitized environment can also lose
`/opt/homebrew/bin` entirely.

Revisit:

- Use one runtime resolver for startup, validation, debug, corpus, audit, and capture.
- Print selected executable, version, source root, and reason once per run.
- Always import the active worktree's `src`, including when using primary's `.venv`.
- Fail preflight on unsupported Node instead of warning and failing later in `npx`.
- Resolve the current PowerShell executable to an absolute path for every child process.
- Diagnose a missing or incomplete environment concisely without dumping an expected
  fallback traceback.
- Make frontend dependency sharing explicit and verify links before startup.

### 4. Stack lifecycle and readiness are ambiguous

Foreground runs depend on the launching terminal. Detached runs do not consistently
record the child PID or preserve the launcher's repaired environment. Retained logs
contain exit code 137 and `The pipeline has been stopped`, which do not explain whether
the owner stopped the stack, the agent terminal disappeared, or a child crashed.

Startup readiness is uneven. Expected connection refusals during polling appear as
PowerShell terminating errors in many otherwise normal logs. Some flows use API health
as the decision to start the entire stack even when SPA or Labs is dead. Primary and
sandbox services have different bind families, making `127.0.0.1` versus `localhost`
observable in probes and capture tools.

Revisit:

- Persist runner PID, process start time, command, worktree, ports, and log paths.
- Make detached stacks survive caller terminal cleanup and make `Stop` target only the
  recorded process tree.
- Probe API, SPA, and Labs independently with bounded timeouts and child-exit checks.
- Detect and repair a partial stack rather than waiting for services that were not
  restarted.
- Treat expected readiness misses as quiet progress, not transcript errors.
- Standardize local probe hosts and account for IPv4/IPv6 binding intentionally.
- End startup with URLs and explicit readiness for every service.

### 5. Port cleanup can affect unrelated processes

The primary stack currently force-stops listeners on configured ports based on port
number alone. This prevents many address-in-use failures but can terminate another
application with no ownership proof. Sandbox stop and cleanup contain more ownership
logic, but behavior is not uniform.

Revisit:

- Record service ownership when starting processes.
- Inspect PID, command line, start time, and worktree before stopping a listener.
- Automatically stop only a verified stale Tripplanner process.
- Report unrelated listeners and require explicit approval before terminating them.
- Verify all ports are released and print the owning process when they are not.

### 6. Logs look alarming during success and incomplete during failure

The shared logger supports terminal outcomes, but many scripts do not guarantee a
`Stop-RunLog` call from `finally`. The run index consequently has many `started`
records without a matching completion or failure. Native tools can bypass PowerShell
transcripts unless invoked through the logged-native helper. Concurrent runs create
`.pid`, `.1`, and `.2` files without a single clear pointer to the relevant run.

Expected health polling fills transcripts with `PS>TerminatingError(...): Connection
refused`. Conversely, actual child failures may appear only as `pipeline has been
stopped` or an exit code without the child command and last useful output.

Revisit:

- Wrap every entry point in one outcome-owning `try/catch/finally` boundary.
- Record exactly one terminal state and elapsed time in the index.
- Distinguish active, interrupted, queued, partial, completed, and failed runs.
- Capture native stdout, stderr, command, exit code, and duration consistently.
- Keep expected polling noise out of normal transcripts.
- Maintain a machine-readable pointer to the latest run of each command and expose a
  simple command that summarizes the last failure and recovery action.
- Include the affected lane, branch/SHA, process, ports, data target, and whether any
  remote or destructive action already occurred.

### 7. Errors report implementation detail instead of recovery

PowerShell source locations and full exception formatting dominate owner-visible
output. Common failures omit changed file names, state classification, ownership,
remote outcome, and a safe next command. Better conflict and incomplete-cleanup
messages already demonstrate the desired pattern but are not used consistently.

Revisit:

- Separate a one-paragraph owner error from verbose diagnostic detail in the log.
- For each expected failure, print: what failed, what succeeded, what was untouched,
  the exact blocking objects, and one recovery command.
- Avoid prescribing destructive `stash`, reset, kill, or force operations without
  showing their impact.
- Give validation failures a concise first cause before framework stack traces.
- Use stable error codes so tests and automation do not depend on prose or line numbers.

### 8. Platform support relies on accumulated fallbacks rather than gates

Historical macOS cleanup failed because `Get-NetTCPConnection` was called where it did
not exist. Current scripts contain Windows and macOS branches for networking, process
trees, reparse points, paths, and executable discovery, but there is no host-level
workflow test proving all daily commands remain portable.

Revisit:

- Run create, serve, readiness, stop, update, conflict recovery, merge, discard, stale
  port cleanup, and locked-directory recovery smoke tests on Windows and macOS.
- Ensure unsupported commands are never evaluated on the other platform.
- Keep one PowerShell implementation where practical and thin launchers only.
- Date-stamp the support matrix and distinguish verified support from intended support.
- Verify executable bits, argument forwarding, spaces in paths, quoting, and exit-code
  propagation for `.command` and `.cmd` pairs.

### 9. Owner-facing names and documentation drift from behavior

The launcher called `Promote-Sandbox` intentionally defaults to the engine's keep-alive
merge behavior, while `-Discard` selects engine promotion and retirement. Some command
tables and older guidance still describe Promote as always discarding. Logs also show
commands launched from retired worker paths and several historical launcher locations,
which makes the active owner unclear.

Revisit:

- Maintain one generated or tested command table for both platform launchers.
- Explain launcher names separately from internal PowerShell parameter-set names.
- Keep examples aligned with keep-alive default and explicit `-Discard` behavior.
- Detect retired or unregistered worktree launch paths and redirect to the canonical
  owner rather than silently running copied script versions.
- Add `--help`/PowerShell help examples for the common owner workflow, not only engine
  implementation terminology.

### 10. Paid, destructive, and data-targeting operations need stronger truth

`build-corpus.ps1` currently says it reads stored trips with no model calls, provider
calls, or trip writes. Its Python implementation explicitly generates trips with the
real planner and says `Spends money`. This is direct cost and expectation friction.
Other debug, restore, sync, and cleanup tools target different emulator databases or
can delete data, so target disclosure must be consistent.

Revisit:

- Correct `Build-Corpus` help and README to disclose model/provider calls, corpus and
  ledger writes, measured versus estimated cost, cumulative cap, and resumability.
- Require an explicit per-run budget or approval for paid execution; keep dry-run free
  and side-effect-free.
- Print database, endpoint, source, destination, estimated scope, and destructive
  effects before restore, clear, seed, drop, or corpus generation.
- Use typed confirmation only for irreversible or paid actions; do not add prompts to
  safe idempotent daily commands.
- Summarize produced records, actual spend, remaining budget, and output paths.

## Inferred Risks to Verify During Revisit

These risks are reachable from current structure but should be reproduced before being
called defects:

- Concurrent registry writers can lose entries or truncate `sandboxes.json`.
- Two sync or promotion commands can race on primary, remote branches, or Lab records.
- A process occupying a Tripplanner port can be unrelated and still be terminated.
- A healthy API with dead SPA/Labs can prevent a clean full-stack restart.
- A command can mutate generated artifacts before confirmation or during `-WhatIf`.
- Nested or concurrent transcripts can make the wrong file appear to be the latest run.
- Copied scripts in stale worktrees can run older behavior against the shared registry.

## Validation Matrix

A future daily-script reliability milestone should automate at least:

- Launch every owner command from repo root, a sandbox, its launcher directory, and a
  path containing spaces.
- Run with missing `pwsh`, incompatible Node, missing `.venv`, incomplete `.venv`, and
  absent frontend dependencies; verify one actionable preflight report.
- Start with each service port free, owned by stale Tripplanner, and owned by an
  unrelated process.
- Start from no stack, a healthy stack, and every partial-stack combination.
- Interrupt foreground and detached startup at each phase and verify status plus cleanup.
- Exercise dirty, ahead, behind, diverged, conflicted, and stale-tracking Git states.
- Run two safe read commands concurrently and two mutating commands concurrently.
- Simulate native child failure, readiness timeout, log lock, and registry write failure.
- Verify `-WhatIf`, dry-run, and declined confirmation produce no side effects.
- Verify paid and destructive commands disclose target and scope before mutation.
- Verify every failure has a stable code, concise owner message, detailed log, and exact
  non-destructive recovery command.
- Execute the core sandbox lifecycle on current Windows and macOS hosts.

## Suggested Revisit Order

1. Define the common command contract, structured outcome, and error format.
2. Centralize repository/lane, runtime, process, port, and data-target preflight.
3. Make logging complete and quiet during expected waits.
4. Make source-control and registry mutations locked, exact-SHA, and resumable.
5. Make stack lifecycle ownership explicit and partial-stack recovery deterministic.
6. Correct paid/destructive help and documentation.
7. Add cross-platform workflow tests before removing accumulated fallbacks.
