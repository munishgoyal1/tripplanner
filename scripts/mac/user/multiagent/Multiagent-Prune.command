#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../../.." && pwd)"
TRIPPLANNER_REPO_ROOT="$repo_root"
. "$repo_root/scripts/mac/lib/pwsh.sh"
require_pwsh

args=()
for arg in "$@"; do
    if [[ "$arg" == "-DryRun" ]]; then
        args+=("--dry-run")
    else
        args+=("$arg")
    fi
done
exec "$PWSH_BIN" -NoProfile -File "$repo_root/scripts/dev/multiagent.ps1" prune "${args[@]}"