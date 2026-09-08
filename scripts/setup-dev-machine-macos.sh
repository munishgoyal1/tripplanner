#!/bin/bash
set -euo pipefail

include_mobile=false
skip_tool_install=false
skip_dependency_install=false

for argument in "$@"; do
  case "$argument" in
    --include-mobile) include_mobile=true ;;
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
pip_index_url="${PIP_INDEX_URL:-https://pypi.org/simple}"
npm_registry_url="${NPM_CONFIG_REGISTRY:-https://registry.npmjs.org/}"

assert_independent_package_source() {
  local source_name="$1"
  local source_url
  source_url="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"
  if [[ "$source_url" == *"pkgs.visualstudio.com"* || "$source_url" == *"1es-public"* ]]; then
    echo "$source_name must not use Microsoft corporate package infrastructure: $2" >&2
    exit 1
  fi
}

assert_independent_package_source "PIP_INDEX_URL" "$pip_index_url"
assert_independent_package_source "NPM_CONFIG_REGISTRY" "$npm_registry_url"

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
  brew_prefix=/opt/homebrew
elif [[ -x /usr/local/bin/brew ]]; then
  brew_prefix=/usr/local
else
  brew_prefix=""
fi

if [[ -n "$brew_prefix" ]]; then
  eval "$("$brew_prefix/bin/brew" shellenv)"
  # `brew shellenv` prints nothing when it is already inside a brew command, and
  # brew sanitizes PATH for its children, so the bin directory can still be absent.
  case ":$PATH:" in
    *":$brew_prefix/bin:"*) ;;
    *) export PATH="$brew_prefix/bin:$brew_prefix/sbin:$PATH" ;;
  esac
fi

if [[ "$skip_tool_install" == false ]]; then
  if brew tap | grep -qx "powershell/tap"; then
    echo "[migrate] Archived PowerShell Homebrew tap"
    brew untap --force powershell/tap
  fi
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
  npm install --global @github/copilot --registry="$npm_registry_url"
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
  local requirements_lock="$repo_root/requirements.lock"

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
    PIP_INDEX_URL="$pip_index_url" "$python_path" -m pip install --quiet --upgrade pip
    PIP_INDEX_URL="$pip_index_url" "$python_path" -m pip install --quiet --progress-bar off \
      -r "$requirements_lock"
    PIP_INDEX_URL="$pip_index_url" "$python_path" -m pip install --quiet \
      -e "$checkout_root" --no-deps
    npm --prefix "$checkout_root/frontend" ci --registry="$npm_registry_url"
    if [[ "$include_mobile" == true ]]; then
      npm --prefix "$checkout_root/mobile" ci --registry="$npm_registry_url"
    fi
  fi

  "$python_path" -c "import fastapi, tripplanner; print('[ok] Python environment')"
  npm --prefix "$checkout_root/frontend" run build
}

setup_dependencies "$repo_root"

echo
echo "Setup complete."
echo "GitHub access: run 'gh auth login' and sign into GitHub in VS Code."
echo "Azure access:  run 'az login' before deployment."
echo "GHCR access:   run 'docker login ghcr.io' before image publication."
echo "Sandbox:      ./scripts/mac/user/sandbox/New-Sandbox.command <name> \"<purpose>\""
if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is installed but not running; start it before local Cosmos or image builds."
fi