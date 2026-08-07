#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$repo_root"
exec pwsh -NoProfile -File "$repo_root/infra/deploy-prod.ps1" "$@"