#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")" && pwd)"
exec "$repo_root/scripts/mac/Open-Tripplanner-Agents.command" "$@"
