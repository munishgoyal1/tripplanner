#!/bin/bash
set -euo pipefail

include_mobile=false
open_agent_windows=false
skip_tool_install=false
skip_dependency_install=false

for argument in "$@"; do
  case "$argument" in
    --include-mobile) include_mobile=true ;;
    --open-agent-windows) open_agent_windows=true ;;
    --skip-tool-install) skip_tool_install=true ;;
    --skip-dependency-install) skip_dependency_install=true ;;
    *) echo "Unknown option: $argument" >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script requires macOS." >&2
  exit 1
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

assert_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$2 is unavailable after installation. Open a new Terminal and rerun setup." >&2
    exit 1
  fi
}

if ! command -v brew >/dev/null 2>&1; then
  if [[ "$skip_tool_install" == true ]]; then
    echo "Homebrew is required and --skip-tool-install was supplied." >&2
    exit 1
  fi
  echo "[install] Homebrew"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

if [[ "$skip_tool_install" == false ]]; then
  echo "[install] Declared Homebrew tools"
  brew bundle --file "$repo_root/devconfigs/macos/Brewfile"
fi

if ! command -v code >/dev/null 2>&1 && [[ -x "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" ]]; then
  export PATH="/Applications/Visual Studio Code.app/Contents/Resources/app/bin:$PATH"
fi

for tool in git node npm python3.13 pwsh code docker gh az; do
  assert_command "$tool" "$tool"
done

echo "Tripplanner macOS developer-machine setup"
pwsh -NoProfile -File "$repo_root/devconfigs/Apply-DevConfigs.ps1" -InstallExtensions

if ! command -v copilot >/dev/null 2>&1; then
  echo "[install] GitHub Copilot CLI"
  npm install --global @github/copilot
else
  echo "[ok] GitHub Copilot CLI"
fi

git -C "$repo_root" config rerere.enabled true
git -C "$repo_root" config rerere.autoupdate true
git -C "$repo_root" config merge.conflictstyle zdiff3
echo "[ok] Git configured for rerere + zdiff3 conflict style"

setup_dependencies() {
  local checkout_root="$1"
  local python_path="$checkout_root/.venv/bin/python"

  if [[ ! -f "$checkout_root/.env" ]]; then
    cp "$checkout_root/.env.example" "$checkout_root/.env"
    echo "[created] $checkout_root/.env from .env.example"
  fi

  if [[ "$skip_dependency_install" == false ]]; then
    if [[ -x "$python_path" ]] && [[ "$($python_path -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.13" ]]; then
      rm -rf "$checkout_root/.venv"
    fi
    if [[ ! -x "$python_path" ]]; then
      python3.13 -m venv "$checkout_root/.venv"
    fi
    "$python_path" -m pip install --upgrade pip
    "$python_path" -m pip install -r "$checkout_root/requirements.lock"
    "$python_path" -m pip install -e "$checkout_root" --no-deps
    npm --prefix "$checkout_root/frontend" ci
    if [[ "$include_mobile" == true ]]; then
      npm --prefix "$checkout_root/mobile" ci
    fi
  fi

  "$python_path" -c "import fastapi, tripplanner; print('[ok] Python environment')"
  npm --prefix "$checkout_root/frontend" run build
}

setup_dependencies "$repo_root"

for worker_name in worker-1 worker-2 worker-3; do
  worker_path="${repo_root}.worktrees/$worker_name"
  if [[ ! -d "$worker_path" ]]; then
    pwsh -NoProfile -File "$repo_root/scripts/dev/agent-worktree.ps1" -Create "$worker_name" -NoOpen
  else
    echo "[ok] Persistent worktree $worker_name"
  fi
  if [[ ! -f "$worker_path/.env" && -f "$repo_root/.env" ]]; then
    cp "$repo_root/.env" "$worker_path/.env"
    echo "[copied] .env from the primary checkout to $worker_name"
  fi
  setup_dependencies "$worker_path"
done

if [[ "$open_agent_windows" == true ]]; then
  for workspace in \
    tripplanner-worker-1.code-workspace \
    tripplanner-worker-2.code-workspace \
    tripplanner-worker-3.code-workspace \
    tripplanner-integration.code-workspace; do
    code --new-window "$repo_root/$workspace"
  done
fi

echo
echo "Setup complete."
echo "GitHub access: run 'gh auth login' and sign into GitHub in VS Code."
echo "Azure access:  run 'az login' before deployment."
echo "GHCR access:   run 'docker login ghcr.io' before image publication."
echo "Agent windows: ./Open-Tripplanner-All-Agents.command"
if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is installed but not running; start it before local Cosmos or image builds."
fi