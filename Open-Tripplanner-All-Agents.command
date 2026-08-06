#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")" && pwd)"
if ! command -v code >/dev/null 2>&1 && [[ -x "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" ]]; then
  export PATH="/Applications/Visual Studio Code.app/Contents/Resources/app/bin:$PATH"
fi
if ! command -v code >/dev/null 2>&1; then
  echo "VS Code command 'code' is unavailable." >&2
  exit 1
fi

for worker_name in worker-1 worker-2 worker-3; do
  if [[ ! -d "${repo_root}.worktrees/$worker_name" ]]; then
    echo "Missing persistent worktree: ${repo_root}.worktrees/$worker_name" >&2
    exit 1
  fi
done

for workspace in \
  tripplanner-worker-1.code-workspace \
  tripplanner-worker-2.code-workspace \
  tripplanner-worker-3.code-workspace \
  tripplanner-integration.code-workspace; do
  code --new-window "$repo_root/$workspace"
done