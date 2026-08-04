# Agent Proposals

Agent-authored proposals for tripplanner. Everything here is a **candidate for
owner review** — a proposal is not implementation approval (see the intake rule
in [FUTURE_FEATURES.md](../../roadmap/FUTURE_FEATURES.md) and the consent rule in
[PRODUCT.md](../../PRODUCT.md) §6). Canonical current behavior still lives in the
`docs/` root documents.

## Folders

| Folder | Contents |
| --- | --- |
| [`feature-proposals/`](feature-proposals/) | New product feature proposals — value, UX, editing, chat, performance, and insight. |
| [`tech-debt/`](tech-debt/) | Performance, race-condition, and maintainability improvement plans. |
| [`dev-workflow/`](dev-workflow/) | Developer workflow and tooling proposals — how features get built, evaluated, and shipped. |

## Start here

- Feature set overview (one-liners): [`feature-proposals/2026-08-04-feature-proposals-summary.md`](feature-proposals/2026-08-04-feature-proposals-summary.md)
- Tech-debt plan: [`tech-debt/2026-08-04-tech-debt-improvement-plan.md`](tech-debt/2026-08-04-tech-debt-improvement-plan.md)
- Feature sandbox workflow: [`dev-workflow/2026-08-04-feature-sandbox-workflow.md`](dev-workflow/2026-08-04-feature-sandbox-workflow.md)

## Conventions

- One dated file per proposal: `YYYY-MM-DD-<slug>.md`.
- Keep folder count small (2–3); group rather than scatter loose files at the root.
- Each feature proposal states the user pain, bounded first version, implementation
  notes against real files, risk, and acceptance — enough to execute later without
  re-deriving intent.
