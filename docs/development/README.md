# Development Guides

This folder explains how humans and coding agents work on the repository. It owns
local setup and collaboration procedures, not product requirements, architecture,
or deployment policy.

- [`dev.md`](dev.md): local application, test, and UX Lab commands.
- [`new-machine-setup.md`](new-machine-setup.md): one-click Windows/macOS toolchain,
  VS Code/Copilot configuration, sandboxes, and manual sign-ins.
- [`architecture-onboarding.md`](architecture-onboarding.md): guided system
  architecture, ownership map, data flows, invariants, and first-week reading plan.
- [`parallel-agent-development.md`](parallel-agent-development.md): sandbox
  worktrees, promotion, and cleanup.
- [`issue-workflow.md`](issue-workflow.md): GitHub issues as the shared task board
  across chat sessions, including claiming, triage and implementation comments,
  and closing.
- [`multiagent-coordination.md`](multiagent-coordination.md): the owner-controlled
  autonomous pipeline — routine issue intake plus explicit approval gates, the
  controller, reusable worker slots, the audit producer, and integration.
- [`setup-oauth.md`](setup-oauth.md): local Google OAuth setup.

Update these guides when the development workflow or commands change. Product
behavior belongs in `docs/PRODUCT.md` or `docs/REQUIREMENTS.md`; production
release procedures belong in `docs/operations/`.
