# Stable UI Versions

Stable UI snapshots are immutable annotated Git tags. They preserve the complete
repository state behind an owner-accepted interface without copying source trees,
keeping long-lived branches, or changing the production deployment. Keep at least
the latest three; older tags are cheap and should not be moved or deleted casually.

## Preserved Versions

| Snapshot | Commit | Interface state |
|---|---|---|
| `ui-stable/2026-07-31-corner-assistant` | `240c2dc` | Current lower-right 480 px Assistant conversation sheet over the usable itinerary/map/details workspace. |
| `ui-stable/2026-07-31-sidecar-assistant` | `cb61af7` | Earlier Assistant sidecar experience with Stop, Copy, and edit-as-new-turn controls. |
| `ui-stable/2026-07-31-itinerary-workspace` | `8da626d` | Pre-sidecar workspace with truthful itinerary timing, compact agenda, Map, and Details. |

These are source restoration points, not proof that an image was deployed to a
particular environment. Production rollback continues to use immutable container
revisions and the guarded deployment runbook.

## List And Preview

List snapshots:

```powershell
.\scripts\dev\stable-ui.ps1 -Action List
```

Open one beside the primary checkout without switching or modifying `master`:

```powershell
.\scripts\dev\stable-ui.ps1 -Action Open `
  -Tag ui-stable/2026-07-31-corner-assistant
```

The helper creates a detached sibling worktree. Install its dependencies and use
noncanonical ports if both versions must run together. Remove it through
`git worktree remove <path>` after comparison.

## Preserve The Next Stable Version

Only create a snapshot after the owner accepts the UI, affected tests/builds pass,
and the milestone is committed and pushed:

```powershell
.\scripts\dev\stable-ui.ps1 -Action Create -Name concise-version-name
```

The helper rejects an uncommitted `HEAD`, creates `ui-stable/<date>-<name>`, and
pushes the tag to GitHub. Labs, drafts, and experiments are not stable snapshots
until explicitly accepted.

## Return To A Version

1. Open the snapshot in a detached worktree and verify the desired behavior.
2. Compare it with current `master`, including frontend contracts and API changes.
3. Restore the intended UI on a normal reviewed branch or focused `master` change;
   do not reset `master` to the old tag.
4. Run current frontend tests and build against current backend contracts.
5. Commit and push the restoration as a new milestone. Canary and production still
   require their normal explicit deployment gates.

This keeps rollback understandable: the tag is immutable evidence, while any return
to it is a new compatibility-checked change rather than destructive history rewrite.