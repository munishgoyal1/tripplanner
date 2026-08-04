# Feature 04 — Chat Quick-Actions, Slash-Commands & Context Chips

- **Pillars:** C (easier chat), A (breezy)
- **Status:** Proposed (new; complements `CHAT-01` structured input)
- **Size:** M · **Risk:** low · **Suggested lane:** Agent 2 (intents) + Agent 1 (chips from state)

## The pain

The blank composer is intimidating and slow. Users don't know what the agent can do or
how to phrase edits, and typing "please move the museum to day 3" is friction. Discovery
and speed both suffer.

## Outcome

The composer offers slash-commands and one-tap context chips derived from the current
selection / day / trip, so most refinements are a click — not a sentence — while still
flowing through the normal retry-safe chat turn (typed data owns the interaction, per taste).

## Bounded v1

- **Slash menu:** `/add`, `/move`, `/swap-hotel`, `/cheaper`, `/more-food`, `/relax-day`,
  `/pack-day`, `/review` — each expands to a prefilled structured mini-form.
- **Context chips** above the composer reflect live state:
  - place selected → "Move <place> to…", "Remove <place>", "Find similar nearby";
  - day focused → "Add lunch to Day 2", "Relax Day 2", "Optimize route".
- Chips/commands emit the same structured intents the agent already handles. **No new
  agent, no free-form-only path.** `/review` stays bound to proposal-only planner review
  (`PLAN-04`).

## UX

- Type `/` → command palette; or tap a chip → prefilled controls → send. Send/Stop
  semantics unchanged. Chips come from workspace state, not model markup.

## Implementation notes

- **Frontend:** composer in `frontend/src/components/ChatPanel.tsx` +
  `AssistantModalShell.tsx`; derive chips from `frontend/src/workspaceState.ts`; reuse
  `TripInputCard`-style structured controls; `frontend/src/hooks/useChatStream.ts` transport
  unchanged.
- **Backend:** map commands to existing tool intents in `src/tripplanner/graph.py` /
  `tools/trip_planner.py`; optionally add a thin intent pass-through so a chip becomes a
  deterministic tool call.

## Perf / privacy / cost

No extra provider calls; chips computed client-side from state.

## Risks & mitigations

- **Command sprawl** → ship a small, curated set; add more only on demand. Low risk.

## Acceptance

- Each command/chip produces the correct prefilled intent and a successful turn.
- `/review` remains proposal-only (no mutation).
- Chips reflect the live selection; nothing bypasses the retry-safe chat path.
