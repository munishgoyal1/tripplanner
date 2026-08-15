# Owner prompt log

`master.txt` is a historical owner prompt log. Automatic prompt appends are
currently paused because changing it leaves the primary `master` worktree dirty
and can block sandbox promotion.

## Entry format

When this flow is explicitly re-enabled by the owner, tail-append new entries.
Until then, do not write to this file.

```
[2026-08-05 17:05] [master] ! Short title of the prompt
<the owner's prompt, verbatim, one or more lines>

```

- The timestamp is local time, `YYYY-MM-DD HH:MM`.
- `!` after `master` marks an important prompt: feature work, a bug fix, critical
  owner direction, or a reusable workflow.
- One blank line between entries.
- Never edit, reorder, or renumber an existing entry.

## Reading the log

```
pwsh -File scripts/dev/show-prompts.ps1              # newest first
pwsh -File scripts/dev/show-prompts.ps1 -Important   # only ! entries
pwsh -File scripts/dev/show-prompts.ps1 -Search hotel -Last 10
```

`scripts/user/Show-Prompts.cmd` is the double-click wrapper.

## History before 5-Aug-2026

Entries `[001]`-`[050]` stay in
[`../prompts_executed.txt`](../prompts_executed.txt) and its curated subset
[`../prompts_executed_imp.txt`](../prompts_executed_imp.txt). Both files are frozen:
read them, never append to them.
