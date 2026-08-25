# Documentation Guide

This directory contains product truth, engineering orientation, operational
runbooks, planning inputs, and historical owner material. Start with the small
canonical set below instead of reading every file.

## Canonical documents

| Document | Purpose | Update when |
| --- | --- | --- |
| [`PRODUCT.md`](PRODUCT.md) | Product intent, scope, interaction rules, and design taste | Vision or product taste changes |
| [`EXPECTED_BEHAVIORS.md`](EXPECTED_BEHAVIORS.md) | Authoritative user actions and observable outcomes, with stable regression IDs | Observable behavior changes or a regression contract is added |
| [`REQUIREMENTS.md`](REQUIREMENTS.md) | Implemented capability baseline, explicit gaps, and near-term roadmap | Shipped capability or status changes |
| [`CODEMAP.md`](CODEMAP.md) | Code ownership, architecture, contracts, and commands | File layout or technical contracts change |
| [`ENGINEERING_LEARNINGS.md`](ENGINEERING_LEARNINGS.md) | Durable lessons from observed failures | A reusable engineering lesson is proven |

## Product planning

| Location | Purpose |
| --- | --- |
| [`roadmap/`](roadmap/README.md) | Possible future outcomes and deferred decisions; never implementation approval |
| [`feature-briefs/`](feature-briefs/README.md) | One owner-approved outcome translated into bounded scope and acceptance criteria |
| [`ux-experiments/`](ux-experiments/README.md) | Isolated visual decisions tested before production implementation |
| [`research/`](research/) | Dated external findings — market and competitive landscape, provider access, cost, and terms — that inform a decision but are not themselves approval |

## How planning becomes current truth

1. Capture an unselected future idea in `roadmap/`.
2. When the owner selects an outcome, define its bounded implementation scope in
  `feature-briefs/`.
3. If the uncertainty is visual, compare explicit options in `ux-experiments/`
  and record the owner's selection before changing production UI.
4. Implement and validate the approved scope.
5. Update `REQUIREMENTS.md` for shipped capability, `PRODUCT.md` for durable
  product intent, and `CODEMAP.md` for changed architecture or ownership.
6. Record reusable failure lessons in `ENGINEERING_LEARNINGS.md` and dated
  rationale in `reference/history/requirements-log.txt`.

Roadmap entries answer "what might be next." Feature briefs answer "what exactly
are we approving now." UX experiments answer "which presentation should we
choose." Canonical documents answer "what is true now."

## Development

| Document | Purpose |
| --- | --- |
| [`development/`](development/README.md) | Scope and index for contributor workflow guides |
| [`development/architecture-onboarding.md`](development/architecture-onboarding.md) | Guided architecture and codebase onboarding for new engineers |
| [`development/dev.md`](development/dev.md) | Local development guidance |
| [`development/new-machine-setup.md`](development/new-machine-setup.md) | Reproduce the Windows/macOS toolchain, VS Code/Copilot settings, and four-agent layout |
| [`development/parallel-agent-development.md`](development/parallel-agent-development.md) | Parallel coding-agent worktrees, merge checkpoints, and VS Code voice input |
| [`development/issue-workflow.md`](development/issue-workflow.md) | GitHub issues as the shared task board across agent sessions: claiming, triage, implementation, and closing |
| [`development/multiagent-coordination.md`](development/multiagent-coordination.md) | Owner-controlled autonomous pipeline: routine issue intake, explicit feature approval gates, controller, workers, audit producer, integration |
| [`development/setup-oauth.md`](development/setup-oauth.md) | Google OAuth setup |
| [`eng-backlog/`](eng-backlog/README.md) | Deferred developer-tooling and engineering-reliability work; not active implementation scope |

Completed backlog lifecycle: when an approved feature or engineering backlog item
is fully implemented, validated, and its canonical documentation is updated, move
the complete entry to [`implemented/`](implemented/README.md) in the same completion
commit. Drafts, partial foundations, deferred work, and items with outstanding
acceptance criteria stay in their active backlog folder.

## Operations

| Document | Purpose |
| --- | --- |
| [`operations/deployment-flow.md`](operations/deployment-flow.md) | Canonical canary, production, monitoring, and rollback flow |
| [`operations/operations-slos.md`](operations/operations-slos.md) | Production observability, SLOs, and Log Analytics queries |
| [`operations/product-analytics.md`](operations/product-analytics.md) | GA4 setup, privacy boundary, events, and activation funnel |
| [`operations/performance-cost.md`](operations/performance-cost.md) | Performance and cost evidence layers and regression baseline |
| [`operations/backup-recovery.md`](operations/backup-recovery.md) | Guarded backup, validation, restore, and recovery-drill procedure |

## Mobile

| Document | Purpose |
| --- | --- |
| [`mobile/ios-testing.md`](mobile/ios-testing.md) | iPhone and iOS testing runbook |
| [`mobile/android-testing.md`](mobile/android-testing.md) | Android testing runbook |

Infrastructure topology, IaC, and guarded data operations remain under
[`../infra/`](../infra/), with [`../infra/README.md`](../infra/README.md) as the
entry point. Local setup, development workflow, diagnostics, and convenience
utilities remain under [`../scripts/`](../scripts/README.md). Release procedures
belong in the canonical operations runbook. Mobile package-specific setup remains in
[`../mobile/README.md`](../mobile/README.md).

## Reference source material

Original owner inputs and chronological context live together under
[`reference/`](reference/README.md). Its index records every source file, its
purpose, authority, and whether consolidation or removal still needs owner
approval. Canonical documents above remain the current implementation truth.

The temporary Office lock file `~$quirements.docx` should not be treated as
source material and may be removed when no editor owns it. Do not move the
active Word document while that lock exists.

## Structure policy

- Keep the canonical documents listed above at the `docs/` root for stable,
  prominent paths.
- Put future product candidates in `docs/roadmap/`.
- Put active milestone intake in `docs/feature-briefs/`.
- Put UX experiments in `docs/ux-experiments/`.
- Put dated external research in `docs/research/`, and state the verification
  date in the document so a stale finding is obvious.
- Put local setup and contributor workflows in `docs/development/`.
- Put deferred cross-cutting developer-tooling and reliability work in
  `docs/eng-backlog/`.
- Put deployment, reliability, observability, and performance runbooks in
  `docs/operations/`.
- Put native-platform testing runbooks in `docs/mobile/`.
- Put original owner inputs, dated history, and inactive owner-driven artifacts
  under `docs/reference/`.
- Keep Azure-mutating infrastructure operations in `infra/` and local developer
  workflow or convenience helpers in `scripts/`.
- Move runbook paths only as a coordinated change that updates every script,
  README, agent instruction, and historical reference.
- Add a new top-level docs folder only when at least two durable documents share
  a clear owner and lifecycle.
- Prefer updating an existing canonical document over creating another summary.
