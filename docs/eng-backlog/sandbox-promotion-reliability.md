# Sandbox Promotion Reliability

Status: Deferred  
Recorded: 2026-08-15  
Owner surface: `scripts/dev/sandbox.ps1` and sandbox launchers

## Intentional behavior

`Promote-Sandbox` defaults to landing work while retaining and resynchronizing the
sandbox. Passing `-Discard` selects discard-after-landing behavior. This keep-alive
default is intentional and is not part of this revisit.

## Problem

The landing workflow correctly uses pull requests, validates the sandbox, verifies
remote ancestry, protects uncommitted sandbox work, and preserves conflict state.
However, remote merge, local-primary synchronization, Lab bookkeeping, registry
mutation, and cleanup currently form one loosely coupled transaction. A local or
post-merge failure can therefore report promotion as failed after remote master has
already advanced, and concurrent activity can change which commit was actually
validated or overwrite local bookkeeping.

Treat remote landing as the authoritative operation. Local synchronization,
bookkeeping, sandbox resynchronization, and optional cleanup should be explicit,
resumable post-merge phases.

## Backlog

### P0: Correctness and transaction boundaries

- Decouple remote landing success from local primary checkout state. A dirty primary
  must not block a conflict-free remote PR merge or turn a completed remote merge into
  a failed promotion. Skip local synchronization with a clear warning when necessary.
- Do not leave completion bookkeeping as uncommitted primary work. Prefer durable
  external promotion state or a separate, conflict-aware publication step over a
  direct primary mutation inside the landing transaction.
- Freeze one candidate commit after all generated metadata commits. Validate that
  exact SHA, push that SHA, require the PR head to match it, and verify that exact SHA
  is contained in `origin/master` after merge.
- Prevent concurrent promotions and registry writers with a repository-scoped lock.
  Write `sandboxes.json` through a temporary file followed by an atomic replacement.
- Record durable phases such as `candidate`, `pr-created`, `queued`, `merged`,
  `verified`, `bookkeeping-pending`, and `cleanup-pending`. A rerun should resume from
  the first incomplete phase rather than replaying completed remote operations.

### P1: Merge behavior and recovery

- Use one landing transaction for keep-alive and discard modes. Retain versus discard
  should be a final policy choice, not two duplicated implementations.
- Give both modes the same synchronization and conflict-recovery path. In particular,
  discard-after-landing should use the same resolver-and-retry helper as keep-alive.
- Handle GitHub merge queues and auto-merge explicitly. Confirm the PR reaches
  `MERGED`, with the expected head SHA, before remote verification or cleanup. A queued
  PR should produce a queued result rather than a false failure.
- Recheck sandbox cleanliness and candidate identity at each mutating boundary. A new
  commit during validation must not be silently included in the merged branch.
- Make post-merge failures truthful: distinguish `remote merged, local sync pending`,
  `remote merged, bookkeeping pending`, and `remote merged, cleanup pending` from a
  failure to merge.

### P2: Side effects and maintainability

- Move generated debug-archive commits and every other mutation after `ShouldProcess`.
  `-WhatIf` and declined confirmation must not delete, stage, or commit files.
- Keep fetch-only preflight separate from mutating synchronization. `-NoSync` semantics
  should be unambiguous and consistent across launchers and direct script invocation.
- Replace source-string assertions with behavior-level tests. Source-shape tests should
  not preserve local-primary coupling or duplicated control flow.
- Keep run logs, warnings, and final status explicit about the remote result, validated
  SHA, PR number, local-primary state, retained/discarded state, and recovery command.

## Target transaction

```text
preflight
  -> acquire repository promotion lock
  -> fetch remote base without mutating primary
  -> synchronize sandbox and recover known conflicts
  -> create generated metadata commits
  -> freeze candidate SHA
  -> validate candidate SHA
  -> push exact SHA and verify remote branch head
  -> create or reuse PR for that head
  -> merge or queue with expected-head protection
  -> wait for and verify remote containment
  -> persist promotion result
  -> best-effort local primary synchronization
  -> retain and resynchronize sandbox, or discard when explicitly requested
  -> release lock
```

The remote verification boundary is the point at which landing succeeds. Every phase
after it must be retryable without re-merging or losing the sandbox.

## Validation matrix

Before considering this backlog complete, automate at least these scenarios:

- Primary has unrelated tracked or untracked changes while remote promotion succeeds.
- Primary becomes dirty after validation or after the PR merges.
- Sandbox HEAD changes during validation or between push and merge.
- Remote sandbox branch advances independently and the push is rejected safely.
- Two sandboxes attempt promotion concurrently.
- GitHub queues the PR instead of merging it immediately.
- Automatic conflict resolution succeeds, and an unresolved conflict remains recoverable.
- Registry writing is interrupted without corrupting the previous registry.
- Lab bookkeeping fails after remote merge and succeeds on retry without duplication.
- Keep-alive resynchronization fails after remote merge and resumes safely.
- Discard cleanup partially fails and a rerun completes it without losing promotion state.
- `-WhatIf` and declined confirmation leave commits, files, branches, and registry unchanged.

## Revisit notes

Re-read the implementation before starting. Individual symptoms may have been patched
since this entry was recorded, especially completed-Lab-record handling, but symptom
fixes should be evaluated against the transaction model above rather than marked as
full completion by themselves.
