#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
exec pwsh -NoProfile -File "$repo_root/scripts/dev/resolve-sandbox-conflicts.ps1" "$@"