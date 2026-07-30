# Documentation Guide

This directory contains product truth, engineering orientation, operational
runbooks, planning inputs, and historical owner material. Start with the small
canonical set below instead of reading every file.

## Canonical documents

| Document | Purpose | Update when |
|---|---|---|
| [`PRODUCT.md`](PRODUCT.md) | Product intent, scope, interaction rules, and design taste | Vision or product taste changes |
| [`REQUIREMENTS_V2.md`](REQUIREMENTS_V2.md) | Implemented capability baseline, explicit gaps, and near-term roadmap | Shipped capability or status changes |
| [`CODEMAP.md`](CODEMAP.md) | Code ownership, architecture, contracts, and commands | File layout or technical contracts change |
| [`ENGINEERING_LEARNINGS.md`](ENGINEERING_LEARNINGS.md) | Durable lessons from observed failures | A reusable engineering lesson is proven |
| [`../REQUIREMENTS.txt`](../REQUIREMENTS.txt) | Chronological requirement and decision history | A new requirement or decision is made |

## Product planning

| Location | Purpose |
|---|---|
| [`roadmap/FUTURE_FEATURES.md`](roadmap/FUTURE_FEATURES.md) | Consolidated future feature and enhancement candidates; not implementation approval |
| [`feature-briefs/NEXT_INCREMENT.md`](feature-briefs/NEXT_INCREMENT.md) | Owner-editable scope for the next coherent milestone |
| [`feature-briefs/FEATURE_BRIEF_TEMPLATE.md`](feature-briefs/FEATURE_BRIEF_TEMPLATE.md) | Full feature-brief template and acceptance structure |
| [`roadmap/DEFERRED_DECISIONS.md`](roadmap/DEFERRED_DECISIONS.md) | Deliberately postponed decisions awaiting evidence or approval |
| [`ux-experiments/`](ux-experiments/) | Bounded UX experiment records and template |

## Development

| Document | Purpose |
|---|---|
| [`development/dev.md`](development/dev.md) | Local development guidance |
| [`development/parallel-agent-development.md`](development/parallel-agent-development.md) | Parallel coding-agent worktrees, merge checkpoints, and VS Code voice input |
| [`development/setup-oauth.md`](development/setup-oauth.md) | Google OAuth setup |

## Operations

| Document | Purpose |
|---|---|
| [`operations/deployment-flow.md`](operations/deployment-flow.md) | Canonical canary, production, monitoring, and rollback flow |
| [`operations/operations-slos.md`](operations/operations-slos.md) | Production observability, SLOs, and Log Analytics queries |
| [`operations/performance-cost.md`](operations/performance-cost.md) | Performance and cost evidence layers and regression baseline |
| [`operations/backup-recovery.md`](operations/backup-recovery.md) | Guarded backup, validation, restore, and recovery-drill procedure |

## Mobile

| Document | Purpose |
|---|---|
| [`mobile/ios-testing.md`](mobile/ios-testing.md) | iPhone and iOS testing runbook |
| [`mobile/android-testing.md`](mobile/android-testing.md) | Android testing runbook |

Infrastructure-specific deployment details remain under
[`../infra/`](../infra/), with [`../infra/README.md`](../infra/README.md) as the
entry point. Mobile package-specific setup remains in
[`../mobile/README.md`](../mobile/README.md).

## Owner and historical artifacts

The Word and text files below are owner inputs or historical reference
material, not current implementation truth:

- [`Requirements.docx`](Requirements.docx) remains at the root while it is an
  active owner input.
- [`archive/Bugs to resolve.docx`](archive/Bugs%20to%20resolve.docx)
- [`archive/deployment_detail.txt`](archive/deployment_detail.txt)
- [`archive/prompts.txt`](archive/prompts.txt)
- [`archive/usage.txt`](archive/usage.txt)

The temporary Office lock file `~$quirements.docx` should not be treated as
source material and may be removed when no editor owns it. Do not move the
active Word document while that lock exists.

## Structure policy

- Keep the canonical documents listed above at the `docs/` root for stable,
  prominent paths.
- Put future product candidates in `docs/roadmap/`.
- Put active milestone intake in `docs/feature-briefs/`.
- Put UX experiments in `docs/ux-experiments/`.
- Put local setup and contributor workflows in `docs/development/`.
- Put deployment, reliability, observability, and performance runbooks in
  `docs/operations/`.
- Put native-platform testing runbooks in `docs/mobile/`.
- Put inactive owner inputs and historical artifacts in `docs/archive/`.
- Move runbook paths only as a coordinated change that updates every script,
  README, agent instruction, and historical reference.
- Add a new top-level docs folder only when at least two durable documents share
  a clear owner and lifecycle.
- Prefer updating an existing canonical document over creating another summary.
