#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../../.." && pwd)"

# Deliberately not routed through pwsh: this launcher must keep working when the
# PowerShell host is broken, which is exactly when the quality loop is needed.
python_bin="$repo_root/.venv/bin/python"
if [ ! -x "$python_bin" ]; then
    common_dir="$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -n "$common_dir" ]; then
        python_bin="$(dirname "$common_dir")/.venv/bin/python"
    fi
fi
if [ ! -x "$python_bin" ]; then
    python_bin="$(command -v python3)"
fi

exec "$python_bin" -u "$repo_root/scripts/dev/multiagent.py" quality-loop "$@"
