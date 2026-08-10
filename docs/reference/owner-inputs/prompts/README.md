# Owner prompt log

`master.txt` is the active owner prompt log. The primary workspace appends every
owner prompt to it, so the sandbox-first workflow has one chronological record.

## Entry format

Tail-append. Newest entries go at the **bottom**, so writing one costs no read of
the file and needs no coordination with any other lane.

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
