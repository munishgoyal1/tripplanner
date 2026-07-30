# Deferred Decisions

This log records product choices that are intentionally left in observation,
need more usage before implementation, or require future owner/agent alignment.
It is not a backlog of automatically approved work. Do not implement an item
until its revisit trigger occurs and the owner confirms the direction.

## Under Observation

### Place-level map zoom

- **Recorded**: 2026-07-26
- **Status**: Keep current behavior and observe in normal use.
- **Current alignment**: Clicking an itinerary place or map pin focuses that
  exact place and pans the map to zoom 15. Keep this behavior for now.
- **Context**: Number-only marker highlighting was added, then its focus
  regression was repaired. Exact-place zoom is now reliable, but it may remove
  too much day-route context for some planning workflows.
- **Revisit trigger**: The owner reports that exact-place zoom feels too tight
  or asks to restore more circuit context after real usage.
- **Options to evaluate then**: retain zoom 15; fit the whole day circuit while
  highlighting the selected number; or use an adaptive zoom based on circuit
  spread.
- **Next action**: None until the revisit trigger occurs.

## Future TODOs

- [ ] Reassess place-level zoom after enough real itinerary editing usage; do
  not change it proactively.

## Entry Template

### Decision title

- **Recorded**: YYYY-MM-DD
- **Status**: Observe / Needs alignment / Deferred
- **Current alignment**: What remains true now.
- **Context**: Why this is not being implemented yet.
- **Revisit trigger**: Concrete signal that should reopen the decision.
- **Options to evaluate then**: Plausible directions, without choosing early.
- **Next action**: Usually none until the trigger occurs.
