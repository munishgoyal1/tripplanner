# Chat agent and workspace layout

## Meta

- Branch: `agents/worker-2`
- Owner: Munish Goyal
- Date started: 5-Aug-2026
- Date ended: pending
- Status: In evaluation
- Lab: `http://127.0.0.1:5175/lab-16-chat-agent-workspace.html`
- Full-size preview: append `?preview=conversation-dock`, `?preview=focus-composer`, or
  `?preview=turn-thread`

## Hypothesis

The Assistant is the panel that builds the trip, but it is presented as the panel most
easily dismissed. Lab #4 settled it into a corner sheet that overlaps the workspace, so
reading the conversation and seeing the plan it just changed are mutually exclusive.
Three further defects compound this: the transcript is bounded and silently loses older
turns, every streaming token drags the reader back to the newest message, and the elapsed
time of a reply is discarded the moment the turn completes.

If the conversation is given a real, permanent place in the workspace, and a turn carries
its own duration and the stops it changed, then a multi-day planning session becomes
reviewable and navigable instead of a scrolling log that has to be closed to be acted on.

## Variants

- **A · Conversation dock.** The Assistant becomes a fourth resident column on the left,
  full height, never dismissed. Itinerary, Map, and Details compress to make room.
  *Exact delta:* it permanently costs about 22 rem of workspace width. Unlike B nothing is
  reclaimed at rest; unlike C Details keeps its own rail.
- **B · Focus composer.** At rest the Assistant is a 4 rem command line beneath the
  workspace with the last reply summarised inline. Expanding it raises a centred reading
  sheet over the workspace. *Exact delta:* zero column cost at rest, but the conversation
  is never side by side with the map.
- **C · Turn thread.** The Assistant is a right rail of turn cards, each showing its
  duration, the tools it ran, and links to the stops it changed. Details becomes an
  on-demand overlay on the map. *Exact delta:* the conversation gains a permanent 26 rem
  rail by taking the space Details holds today.

## Required in every option

These are defects, not choices, so all three options implement them identically:

1. The session keeps every turn, grouped by when it happened.
2. Scroll position belongs to the reader; a new reply offers *Jump to latest* instead of
   seizing the viewport.
3. Every answered turn keeps a badge with the seconds it took; the running turn shows a
   live counter that settles into that badge.
4. Every reply lists the stops it changed, and selecting one moves Itinerary, Map, and
   Details to that stop.

## Scope

- Changed experiment files:
  - `frontend/labs/lab-16-chat-agent-workspace.html`
  - `frontend/labs/src/chat-agent-workspace/main.tsx`
  - `frontend/labs/src/chat-agent-workspace/ChatWorkspace.tsx`
  - `frontend/labs/src/chat-agent-workspace/fixture.ts`
  - `frontend/labs/src/shared/labRecords.ts`, `LabScope.tsx`, `vite.config.ts` (registration)
- Related production code, read but not modified:
  - `frontend/src/components/ChatPanel.tsx` — the unconditional scroll-to-newest effect
    and the history restore that drops timing metadata.
  - `frontend/src/hooks/useChatStream.ts` — `elapsedLabel` exists only while streaming.
  - `src/tripplanner/web/chat_store.py` — `_MAX_TURNS = 80` truncates persisted history.
- Non-goals: agent behavior, tool selection, phase gating, the SSE contract, Itinerary,
  Map, and Details content design, and any change to server-side persistence limits.

## Interaction intent

A planning session lasts days, not minutes. The Assistant should read as a ledger of
decisions with their cost and consequences attached, so the owner can ask "why is the
museum skipped on Friday" three days later and land on the answer and the stop together.
Nothing in the conversation should require dismissing the plan to read it.

## Test scenarios

1. Scroll to the top of the transcript in each option; confirm the earliest turn from two
   days ago is present and labelled.
2. Scroll up, press Send, and confirm the view holds position and offers *Jump to latest*.
3. Watch a live turn's counter and confirm the same duration is retained after it settles.
4. Select an effect chip on an older reply and confirm Itinerary, Map, and Details follow.
5. Edit the day while a reply is streaming and judge whether the option allows it.
6. Compare the resting width left to Map in each option against today's baseline.

## Scorecard (1-5)

| Criterion | A · Dock | B · Composer | C · Turn thread |
| --- | --- | --- | --- |
| Work and converse at once | | | |
| Cost to the rest of the workspace | | | |
| Speed of finding an old decision | | | |
| Legibility of reply cost | | | |

## Decision

- Decision: Option A · Conversation dock, selected by the owner in the Lab, with two saved
  modifications — the dock expands on the left side and keeps hide/maximize controls, and
  the maximized view carries Option C's per-turn timing and detail.
- Revision after hands-on use: the owner rejected the left column and asked for Option B's
  resting shape. The dock now lives at the bottom of the workspace as a single composer row
  (`layout="bar"`), expands upward into a 58vh conversation sheet or a near-full-height view
  over the workspace, and minimizes back to the single row. Nothing in the core columns moves
  when it expands. The Assistant is always mounted and only hidden with `hidden`, so an
  in-flight turn and the loaded transcript survive a hide/show round trip, and an agent
  question arriving while collapsed opens the sheet automatically.
- Also revised: each turn now renders as a card — the user bubble carries a clock time, and
  the assistant card carries a `Sparkles` + `Assistant` header, the same clock time, and the
  reply duration chip — because the shipped flat list did not match the Lab.
- Implementation: in sandbox `sbx-lab16-chat-dock` (branch `sandbox/lab16-chat-dock`),
  awaiting owner inspection. Production code touched: `App.tsx` (bottom dock, `assistantView`
  state, post-turn selection scope, turn-effect plumbing), `ChatPanel.tsx` (layout modes, turn
  cards, day grouping, reading position, timing badges, changed-stop chips), `useChatStream.ts`
  (turn timing), plus new `turnEffects.ts` and `turnMetadata.ts`. `CanvasPaneFrame.tsx` still
  carries an `Assistant` pane label that the bottom dock no longer uses.
- Selection scope after a turn: a reply that touched one place selects it in Itinerary, Map,
  and Details (a hotel wins over other stops in the same turn); a change spread across days,
  or a brand-new trip, falls back to the all-days summary instead of leaving one day scoped.
- Rationale: the dock gives the core panes their full width while keeping the conversation
  resident instead of a sheet that covers the workspace.
- Next action: owner inspects the sandbox at a window at least 1200px wide, then promotes
  or discards it. Deferred and still owner decisions: the server transcript keeps only the
  last 80 turns, and turn timing plus changed-stop links are stored per browser rather than
  in the transcript contract, so they do not follow the owner to another device.
