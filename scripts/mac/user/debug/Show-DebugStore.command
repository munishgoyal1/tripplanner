#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../../.." && pwd)"
TRIPPLANNER_REPO_ROOT="$repo_root"
. "$repo_root/scripts/mac/lib/pwsh.sh"
require_pwsh
exec "$PWSH_BIN" -NoProfile -File "$repo_root/scripts/dev/debug-store.ps1" show "$@"
