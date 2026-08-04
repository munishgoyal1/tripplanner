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
| [`implemented/`](implemented/) | Proposals that have been built and shipped; kept for provenance. |

## Start here

- Feature set overview (one-liners): [`feature-proposals/2026-08-04-feature-proposals-summary.md`](feature-proposals/2026-08-04-feature-proposals-summary.md)
- Tech-debt plan: [`tech-debt/2026-08-04-tech-debt-improvement-plan.md`](tech-debt/2026-08-04-tech-debt-improvement-plan.md)
- Trip schema versioning (deferred): [`tech-debt/2026-08-04-trip-schema-version-and-migration.md`](tech-debt/2026-08-04-trip-schema-version-and-migration.md)
- Implemented — feature sandbox workflow: [`implemented/2026-08-04-feature-sandbox-workflow.md`](implemented/2026-08-04-feature-sandbox-workflow.md)

## Conventions

- **Numbering:** every new proposal takes the next value from a single incremental
  counter shared across all folders (`feature-proposals/`, `tech-debt/`, `implemented/`).
  **Next number: `ap-14`.** Bump this line whenever you claim a number.
- Name each new proposal `ap-<num>-title.md` and put the `ap-<num>` id on the
  first line of the document (e.g. `# ap-13 — <title>`).
- Pre-convention files (`01`–`09` and dated `YYYY-MM-DD-*`) are grandfathered — leave
  their names as-is.
- Keep folder count small (2–3); group rather than scatter loose files at the root.
- Each feature proposal states the user pain, bounded first version, implementation
  notes against real files, risk, and acceptance — enough to execute later without
  re-deriving intent.
