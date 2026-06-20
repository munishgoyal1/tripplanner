# UX Experiments

This folder tracks A/B-style UX layout experiments so we can compare quickly and discard safely.

## Branch Strategy

- Stable baseline: `master`
- Preserved pre-scroll baseline: `preserve/pre-vertical-scroll` (from commit `3e7df9c`)
- Active experiment branches:
  - `exp/ux-shell-a-map-first`
  - `exp/ux-shell-b-story-first`
  - `exp/ux-shell-c-compact-mobile`

## Rules

1. Keep each experiment isolated to UI layout/interaction files only.
2. Timebox each experiment to 1-2 sessions.
3. Use the scorecard template for decision-making.
4. End each experiment with one decision: `keep` (merge) or `discard` (delete branch).

## Fast Commands

```powershell
git switch exp/ux-shell-a-map-first
git switch exp/ux-shell-b-story-first
git switch exp/ux-shell-c-compact-mobile
git switch preserve/pre-vertical-scroll
git switch master
```

## Compare Checklist

- Task completion speed
- Layout clarity
- Cognitive load
- Mobile usability
- Delight / visual appeal
- Editing confidence
