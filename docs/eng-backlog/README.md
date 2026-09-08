# Engineering Backlog

This folder holds deferred, cross-cutting engineering work that is worth preserving
but is not approved active scope. It is for implementation reliability, developer
tooling, and maintenance concerns rather than product candidates.

When an entry's full approved scope is implemented, validated, and reflected in the
canonical docs, move the entry to [`../implemented/`](../implemented/README.md) in
the same completion commit. Keep partial, deferred, or unapproved work here.

Backlog entries describe the problem, desired properties, and validation evidence.
They are not authorization to implement the work. Re-read the current code and
canonical documentation before starting because the implementation may have changed
since an entry was recorded.

## Entries

| Entry | Area | Status |
| --- | --- | --- |
| [Autonomous agents](autonomous-agent-coordination.md) | Coordination | Approved |
| [Daily script reliability and friction](daily-script-reliability.md) | Owner-facing local workflow, runtimes, processes, logs, and portability | Deferred |
| [Sandbox promotion reliability](sandbox-promotion-reliability.md) | Developer scripts and parallel-agent workflow | Deferred |
| [Lane 3 script audit shortlist](lane-3-script-audit-shortlist.md) | Owner review shortlist derived from the script reliability entries | Awaiting signoff |
