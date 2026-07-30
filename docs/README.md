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
| [`DEFERRED_DECISIONS.md`](DEFERRED_DECISIONS.md) | Deliberately postponed decisions awaiting evidence or approval |
| [`ux-experiments/`](ux-experiments/) | Bounded UX experiment records and template |

## Operations and development

| Document | Purpose |
|---|---|
| [`dev.md`](dev.md) | Local development guidance |
| [`parallel-agent-development.md`](parallel-agent-development.md) | Parallel coding-agent worktrees, merge checkpoints, and VS Code voice input |
| [`deployment-flow.md`](deployment-flow.md) | Canonical canary, production, monitoring, and rollback flow |
| [`operations-slos.md`](operations-slos.md) | Production observability, SLOs, and Log Analytics queries |
| [`product-analytics.md`](product-analytics.md) | GA4 setup, privacy boundary, events, and activation funnel |
| [`performance-cost.md`](performance-cost.md) | Performance and cost evidence layers and regression baseline |
| [`backup-recovery.md`](backup-recovery.md) | Guarded backup, validation, restore, and recovery-drill procedure |
| [`setup-oauth.md`](setup-oauth.md) | Google OAuth setup |
| [`ios-testing.md`](ios-testing.md) | iPhone and iOS testing runbook |
| [`android-testing.md`](android-testing.md) | Android testing runbook |

Infrastructure-specific deployment details remain under
[`../infra/`](../infra/), with [`../infra/README.md`](../infra/README.md) as the
entry point. Mobile package-specific setup remains in
[`../mobile/README.md`](../mobile/README.md).

## Owner and historical artifacts

The Word and text files in this directory are owner inputs or historical
reference material, not current implementation truth:

- `Requirements.docx`
- `Bugs to resolve.docx`
- `deployment_detail.txt`
- `prompts.txt`
- `usage.txt`

The temporary Office lock file `~$quirements.docx` should not be treated as
source material and may be removed when no editor owns it. These artifacts stay
at their current paths until the owner explicitly approves archival or deletion;
moving opaque historical inputs without reviewing their contents would create
more uncertainty than structure.

## Structure policy

- Keep the five canonical documents at the `docs/` root for stable, prominent
  paths.
- Put future product candidates in `docs/roadmap/`.
- Put active milestone intake in `docs/feature-briefs/`.
- Put UX experiments in `docs/ux-experiments/`.
- Keep operational runbook paths stable unless a coordinated move updates every
  script, README, agent instruction, and historical reference.
- Add a new top-level docs folder only when at least two durable documents share
  a clear owner and lifecycle.
- Prefer updating an existing canonical document over creating another summary.
