#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../../.." && pwd)"
TRIPPLANNER_REPO_ROOT="$repo_root"
. "$repo_root/scripts/mac/lib/pwsh.sh"
require_pwsh

# Default is keep-alive: land the sandbox's work in the base branch, then
# resync and keep the sandbox registered and active (sandbox.ps1 -Merge).
# Pass -Discard to retire the sandbox after landing instead (sandbox.ps1 -Promote).
verb="-Merge"
args=()
for arg in "$@"; do
  if [ "$arg" = "-Discard" ] || [ "$arg" = "--discard" ]; then
    verb="-Promote"
  else
    args+=("$arg")
  fi
done

# bash 3.2 (macOS default) throws "unbound variable" expanding an empty array
# under set -u, so only splice args in when there are any.
if [ "${#args[@]}" -gt 0 ]; then
  exec "$PWSH_BIN" -NoProfile -File "$repo_root/scripts/dev/sandbox.ps1" "$verb" "${args[@]}"
else
  exec "$PWSH_BIN" -NoProfile -File "$repo_root/scripts/dev/sandbox.ps1" "$verb"
fi