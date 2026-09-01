#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
. "$repo_root/scripts/mac/lib/pwsh.sh"
require_pwsh
cd "$repo_root"
exec "$PWSH_BIN" -NoProfile -File "$repo_root/infra/migration/Invoke-OneClickMigration.ps1" \
  -Operation Provision "$@"