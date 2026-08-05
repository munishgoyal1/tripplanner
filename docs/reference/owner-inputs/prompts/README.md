# Owner prompt log — per-lane files

Every agent lane appends only to its own file here. Two lanes never write the same
file, so these logs can never produce a merge conflict. That is the entire point of
this directory: the previous single shared `prompts_executed.txt` conflicted on
almost every parallel task and burned time and cost on resolving a log nobody
disputes.

| File | Only writer |
| --- | --- |
| `master.txt` | MasterAgent in the primary `master` workspace |
| `worker-1.txt` | Agent 1 - Iti-Map |
| `worker-2.txt` | Agent 2 - Detail-Chat |
| `worker-3.txt` | Agent 3 - Infra |

## Entry format

Tail-append. Newest entries go at the **bottom**, so writing one costs no read of
the file and needs no coordination with any other lane.

```
[2026-08-05 17:05] [worker-2] ! Short title of the prompt
<the owner's prompt, verbatim, one or more lines>

```

- The timestamp is local time, `YYYY-MM-DD HH:MM`. It replaces the old global
  `[NNN]` counter, which forced every lane to read the shared file to find the next
  number and still collided when two lanes picked the same one.
- `!` after the lane marks an important prompt: feature work, a bug fix, critical
  owner direction, or a reusable workflow. It replaces the separate
  `prompts_executed_imp.txt` copy, so an important prompt is written once, not twice.
- One blank line between entries.
- Never edit, reorder, or renumber an existing entry.

## Reading the log

```
pwsh -File scripts/dev/show-prompts.ps1              # all lanes, newest first
pwsh -File scripts/dev/show-prompts.ps1 -Important   # only ! entries
pwsh -File scripts/dev/show-prompts.ps1 -Search hotel -Last 10
```

`scripts/user/Show-Prompts.cmd` is the double-click wrapper.

## History before 5-Aug-2026

Entries `[001]`-`[050]` stay in
[`../prompts_executed.txt`](../prompts_executed.txt) and its curated subset
[`../prompts_executed_imp.txt`](../prompts_executed_imp.txt). Both files are frozen:
read them, never append to them.
