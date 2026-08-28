---
name: Portable Agent Workspace Preferences
description: Keep parallel GitHub Copilot agent work visible and consistently placed.
applyTo: "**"
---
# Agent Workspace Preferences

- Before substantive work after every user prompt, rename the current chat to a
  concrete 4-5 word summary of the latest active task when the host supports it.
- Reconsider the title after every prompt instead of retaining the first task's
  title throughout a long session.
- When direct session renaming is unavailable, prefix every intermediary update
  with `Current task: <4-5 word summary>` so the active assignment remains visible
  near the bottom of the chat.
- Open GitHub Copilot agent chats in the primary editor area when the host allows
  the agent to control placement. Preserve the workspace's restored layout.
- Every substantive final reply and session summary must include a concise
  `Original prompt` section quoting the latest active user request verbatim, so
  the task can be identified without scrolling.
- Every substantive final reply and session summary must include a concise
  `Root cause (RCA)` section. For failures, state the supported direct cause,
  evidence, contributing factors, why the fix works, and remaining risk. For
  work with no failure to diagnose, say RCA is not applicable and give the
  decision rationale instead of inventing a cause.
- Every substantive final reply and session summary must include a concise
  `Next actions` section with ordered steps, their owner, and any validation,
  approval, deployment, or restart required. Write `None` when no follow-up is
  needed.
