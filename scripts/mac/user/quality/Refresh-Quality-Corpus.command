#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../../.." && pwd)"
. "$repo_root/scripts/mac/lib/pwsh.sh"
require_pwsh
exec "$PWSH_BIN" -NoProfile -File "$repo_root/scripts/dev/refresh-audit-corpus.ps1"