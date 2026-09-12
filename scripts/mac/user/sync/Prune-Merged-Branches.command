#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../../.." && pwd)"
TRIPPLANNER_REPO_ROOT="$repo_root"
. "$repo_root/scripts/mac/lib/pwsh.sh"
require_pwsh
if [[ "${1:-}" == "?" || "${1:-}" == "help" ]]; then
  exec "$PWSH_BIN" -NoProfile -File "$repo_root/scripts/dev/show-launcher-help.ps1" prune-merged-branches
fi
exec "$PWSH_BIN" -NoProfile -File "$repo_root/scripts/dev/prune-merged-branches.ps1" "$@"
