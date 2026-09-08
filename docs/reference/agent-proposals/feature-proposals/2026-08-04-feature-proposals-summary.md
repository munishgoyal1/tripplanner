# Feature Proposals — High-Impact Set (2026-08-04)

Status: **Proposed, awaiting owner selection.** Nothing implemented. Per the intake
rule, the owner picks one coherent outcome and scopes it in a feature brief before work.

Author's intent: make the **core plan → refine → trust → act** loop feel breezy and
insightful. The existing backlog ([FUTURE_FEATURES.md](../../../roadmap/FUTURE_FEATURES.md))
leans toward *new capabilities* (live mode, import, collaboration). This set instead
attacks the everyday pains the owner named: easy UX, easy editing across itinerary/map/
details, easier work with the chat agent, breezy performance, and an insightful final
itinerary. All proposals preserve the single-agent architecture, explicit-mutation
control, privacy boundaries, and low operating cost.

## Value pillars (legend)

- **A** — Breezy UX & fast start
- **B** — Easy editing across itinerary, map, and details
- **C** — Easier work with the chat agent
- **D** — Performance: breezy, not laggy
- **E** — Insightful, trustworthy itinerary outcome

## The set (one-liner each)

| # | Feature | Pillars | One-liner | File |
| --- | --- | --- | --- | --- |
| 1 | One-Line Trip Starter & Smart Intake | A, E | Turn a single sentence ("5 days in Kerala with kids next month") into a fully prefilled intake and an automation-first complete plan — kill the blank-canvas start. | [01](01-one-line-trip-starter.md) |
| 2 | Direct-Manipulation Itinerary Editing | B, A | Drag stops between days and reorder them right in the itinerary, with instant deterministic reflow and booked stops locked. | [02](02-direct-manipulation-itinerary-editing.md) |
| 3 | Map-as-Editor | B, A | Make the dominant map a first-class editor: click empty map/POI to add, drag a pin to another day, reshape a day's circuit visually. | [03](03-map-as-editor.md) |
| 4 | Chat Quick-Actions, Slash-Commands & Context Chips | C, A | Slash-commands and one-tap contextual chips ("/cheaper", "swap hotel", "more food on Day 3") so refining never needs a blank prompt. | [04](04-chat-quick-actions-and-chips.md) |
| 5 | Conversational Change Diff & Undo Timeline | C, B, E | Every agent edit shows a plain-language before/after diff and one-click revert to any prior trip revision. | [05](05-conversational-change-diff-and-undo.md) |
| 6 | "Why This?" Provenance & Insight Layer | E, C | Each place, hotel, time, and route carries a compact "why we picked this" tied to your preference and the verified fact behind it. | [06](06-why-this-provenance-insight-layer.md) |
| 7 | Live Itinerary Health Meter & One-Tap Fixes | E, B | An always-visible quality gauge (pace, meals, travel load, booking gaps, budget fit) where each gap links to a one-tap fix. | [07](07-live-itinerary-health-meter.md) |
| 8 | Perceived-Performance & Responsiveness Program | D, A, B | Optimistic instant edits, virtualized lists, hover-prefetch, and memoized map overlays so the workspace feels breezy, never laggy. | [08](08-perceived-performance-program.md) |
| 9 | Itinerary Alternatives & Day A/B Compare | E, B | Generate a few intentional variants (relaxed / packed / foodie / budget) for a day or trip and adopt the best with one click. | [09](09-itinerary-alternatives-and-day-compare.md) |

## Coverage check (every named pain is hit)

- Easy UX / fast start → 1, 4, 8
- Easy editing (itinerary · map · details) → 2, 3, 7, 9
- Easier chat agent → 4, 5, 6
- Breezy performance → 8 (plus optimistic layer feeding 2, 3)
- Insightful outcome → 5, 6, 7, 9

## Suggested sequencing (quality-first, low-risk earns trust early)

1. **Foundations & quick wins:** #8 (perf/optimistic layer — also unblocks smooth
   editing) + #6 (provenance) + #7 (health meter). Mostly low risk, high perceived value.
2. **Editing power:** #2 (itinerary drag) then #3 (map-as-editor) — they share one
   mutation/reflow contract, so build the contract once.
3. **Chat ergonomics & trust:** #4 (quick-actions) + #5 (diff & undo).
4. **Front door & exploration:** #1 (one-line starter) + #9 (alternatives).

## Parallel-lane mapping (if approved for a wave)

- **Agent 1 (Iti-Map / frontend):** #2, #3, #8 UI, chips for #4, meters/diff UI.
- **Agent 2 (Detail-Chat / backend):** #4 intents, #5 diff, #6 rationale, #7 gate
  exposure, #9 variant generator, #1 seed parse.
- **Agent 3 (Infra/storage):** #5 bounded revision snapshots + prune, #8 view-model
  precompute + places_cache batching (shared with the tech-debt P0 fix).

Each item is one PR-sized change with focused tests, validated once per milestone,
then guarded-integrated to master — same flow as the prior refactor wave.

## Open decision for owner

Pick a scope: (a) the sequencing above end-to-end, (b) just step 1 (foundations)
first and review, or (c) a specific subset. Then the selected items get feature
briefs before any code.
