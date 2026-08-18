# Autonomous Agent Coordination

Status: Approved; built, first live batch not yet run  
Recorded: 2026-08-18  
Owner surface: GitHub Issues, agent workers, worktrees, integration, and developer scripts

## Scope

This backlog records a proposed way to let several bounded agent sessions process
GitHub issues with minimal owner coordination while preserving one controlled path
back to `master`. It extends the manual protocol in
[Issue Workflow](../development/issue-workflow.md).

The owner approved this, and the operational contract now lives in
[Multiagent Coordination](../development/multiagent-coordination.md), which
supersedes the open questions below. That brief is the current truth; this entry
remains as the reasoning that produced it.

## Problem

GitHub Issues now provide durable state across isolated chats, but coordination is
still manual. A session must notice queued work, claim it, choose a lane, avoid
collisions, report progress, and arrange integration. Labels are visible but are not
an atomic lock. A pushed worker branch is not proof that its change integrates or
passes the combined validation baseline.

Letting every worker poll and claim independently would distribute those race
conditions rather than solve them. Merging every newly accepted change into every
active worker would also increase conflict churn and invalidate work that does not
depend on the change.

## Desired Outcome

Use GitHub Issues as the queue and audit log, one deterministic coordinator as the
sole dispatcher, lightweight issue worktrees as the default worker boundary, and a
short-lived integration branch as the accepted-work baseline.

```text
GitHub Issues
     |
deterministic coordinator
     |
issue worktree + one bounded worker session
     |
exact worker commit SHA
     |
coordinator integration branch
     |
focused and aggregate validation
     |
one reviewed landing into master
```

Full `sandbox.ps1` environments remain appropriate when work needs an isolated stack,
ports, or Cosmos database. Ordinary documentation, tests, and bounded code changes
should use cheaper issue worktrees that do not consume sandbox slots or appear in
`sandboxes.json`.

## Coordination Contract

### One active coordinator

- One coordinator lease names the process or session allowed to assign work and
  advance the integration branch. The lease expires and can be recovered.
- Workers never discover and claim arbitrary issues. They receive one issue, one
  worktree, one base SHA, and one validation contract from the coordinator.
- Selection, lease expiry, branch creation, state transitions, and exact-SHA
  integration are deterministic operations. Agent reasoning handles triage and code;
  it does not own concurrency control.
- A second coordinator starts only after proving the prior lease expired. Recovery
  must not create a second live dispatcher.

### Issue state

The autonomous flow needs more resolution than the current manual labels provide:

```text
queued
  -> triaging
  -> in-progress
  -> ready-for-integration
  -> integrating
  -> integrated
  -> needs-verify
```

`blocked`, `failed`, or a return to `queued` are explicit side paths. Whether these
become labels, a machine-readable issue block, or both is an implementation decision;
there must still be one unambiguous current state.

The coordinator maintains one editable assignment record containing at least:

- issue number and attempt number;
- coordinator and worker lease identifiers plus expiry times;
- worker session identifier, lane, branch, worktree, and immutable base SHA;
- declared owning paths, related contract surfaces, and dependencies;
- required focused validation and its result;
- worker commit and pushed remote SHA;
- integration SHA and aggregate validation result;
- last heartbeat, terminal outcome, and exact recovery action.

Human-readable Triage and Implementation comments remain the durable explanation.
Machine state should be updated in place rather than appended as a transcript.

### Scheduling and collision control

- Dispatch only issues that are owner-approved or explicitly queued under the current
  policy. A backlog entry alone never enters the execution queue.
- Compare declared files and the ownership/contracts in `docs/CODEMAP.md`. Two issues
  can conflict through a shared API, state owner, generated artifact, append-only log,
  or test fixture even when their file lists do not intersect.
- Serialize issues with overlapping write surfaces or dependencies. Parallelize only
  bounded work with independent acceptance checks.
- Start with one worker, then two or three after lease expiry and crash recovery are
  proven. Concurrency is a capacity limit, not a target.

### Worker contract

Each worker receives a complete, immutable assignment rather than a general request to
watch GitHub:

1. Start from the coordinator's current integration SHA in a new issue worktree.
2. Read the issue, canonical owners, and named nearby code or tests.
3. Update the issue's Triage record before editing when new findings change scope.
4. Change only the assigned outcome and commit it with the issue reference.
5. Run the required focused checks and push the exact commit.
6. Return structured output: terminal state, changed files, validation, commit SHA,
   remote SHA, restart needs, and follow-ups.
7. Stop. The worker never merges itself, closes the issue, or starts another issue.

The installed Copilot CLI can support noninteractive named sessions, resumable session
IDs, JSONL output, explicit permissions, observability, and resource limits. Those
capabilities make supervised headless workers feasible, but the coordinator must treat
the process exit, structured result, Git remote SHA, and tests as separate evidence.

### Integration contract

- Integrate the worker's immutable pushed SHA, never a moving branch head.
- Recheck issue ownership, lease, base, changed paths, and remote SHA before mutation.
- Apply or merge into a short-lived coordinator integration branch and run the focused
  validation there. Advance the accepted baseline only after it passes.
- Run aggregate validation at a bounded batch milestone before proposing the final
  landing into `master`.
- A conflict or focused failure returns to the original worker when its lease is still
  valid. Otherwise record the failed attempt and schedule a fresh worktree from the
  newest accepted baseline.
- Close the issue only when its fix reaches `master`, preserving the current meaning of
  `Fixes #N`. An integrated batch commit is not yet a closed issue.

### Selective synchronization

Do not merge each accepted commit into all live workers. After integration, compare the
accepted change with active assignments:

- unaffected workers continue on their immutable base;
- dependent workers are cancelled and restarted from the new baseline before they
  accumulate more work;
- workers with a possible contract overlap are paused for a deterministic review;
- no worker silently rebases or merges while an agent process is editing its tree.

## Recovery and Safety

- Leases and heartbeats expire. Every coordinator and worker operation is idempotent or
  records a resumable phase before remote mutation.
- A worker timeout stops new commands, captures diagnostics, and leaves the worktree and
  branch available for inspection. It does not immediately delete evidence.
- Reconciliation compares issue state, process state, worktree state, and remote Git
  state after a coordinator restart. GitHub labels alone are insufficient.
- Agent permissions should deny production deployment, secret access, destructive Git,
  arbitrary issue claiming, merge, and push outside the assigned branch.
- Resource caps bound elapsed time, model usage, retries, output size, and concurrent
  workers. A stopped or blocked worker must not loop indefinitely.
- Never place credentials, `.env` contents, trip data, or user data in issue comments or
  worker transcripts.
- Production deployment remains a separate owner-approved operation.

## Staged Rollout

### Stage 1 - Dry-run selector

Read queued issues, parse declared paths and dependencies, detect conflicts, and print
proposed assignments. Do not mutate issues, create branches, or launch agents.

### Stage 2 - One supervised worker

Create one lightweight worktree, launch one bounded noninteractive worker, collect its
structured result, and stop before integration. Exercise timeout and resume behavior.

### Stage 3 - Exact-SHA integration

Integrate one successful worker SHA into a temporary coordinator branch, run focused
validation, and prove retry and rollback behavior without touching `master`.

### Stage 4 - Controlled concurrency

Allow two or three independent assignments. Prove lease recovery, collision deferral,
selective restart, and coordinator crash reconciliation.

### Stage 5 - Final landing

Run aggregate validation and open one coordinator pull request. Keep review and the
actual `master` landing owner-visible; do not enable production deployment.

## Validation Evidence Required

An implementation is not complete until automated tests or reproducible fixtures prove:

- two coordinators cannot hold a valid lease simultaneously;
- two workers cannot own the same issue attempt;
- stale leases recover without duplicating remote mutations;
- overlapping files and declared contract surfaces are not dispatched concurrently;
- a worker cannot push outside its assigned branch or merge itself;
- integration uses the recorded SHA even when the worker branch moves afterward;
- failed focused validation does not advance the accepted baseline;
- coordinator restart reconciles issue, process, worktree, and Git state;
- unaffected workers continue while dependent workers restart selectively;
- aggregate failure blocks the final pull request or clearly marks it unready;
- issues remain open until the accepted commit reaches `master`;
- the same supported orchestration path behaves consistently on Windows and macOS.

## Decisions Deferred Until Implementation Approval

- Coordinator runtime and hosting model: short-lived command, scheduled process, or
  supervised service.
- Lease storage and atomic compare-and-set mechanism.
- Exact issue metadata format and additional state labels.
- Worktree directory, naming, retention, and garbage-collection policy.
- Agent runtime choice per task: Copilot CLI, supervised VS Code agent host, or a
  deliberately small combination.
- Integration strategy: merge commit, cherry-pick, or another exact-SHA operation.
- Aggregate validation size, batch limits, and pull-request policy.
- Whether a runtime-needing task escalates automatically to a full sandbox or waits for
  owner confirmation.

## Non-Goals

- A permanent free-running AI session that independently chooses repository priorities.
- Every worker polling GitHub or negotiating ownership with peer workers.
- Replacing canonical documentation with issue comments or generated summaries.
- Treating labels as an atomic queue, pushed branches as validated work, or broad worker
  synchronization as conflict prevention.
- Deploying to canary or production, changing production data, or bypassing the existing
  owner approval gates.

Tracked by GitHub issue #61.
