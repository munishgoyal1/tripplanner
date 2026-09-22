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

# Discover existing vendor apps and Homebrew before deciding anything is missing.
for bin_dir in /opt/homebrew/bin /opt/homebrew/sbin /usr/local/bin \
  /Library/Frameworks/Python.framework/Versions/3.13/bin \
  "/Applications/Visual Studio Code.app/Contents/Resources/app/bin" \
  "$HOME/Applications/Visual Studio Code.app/Contents/Resources/app/bin" \
  /Applications/Docker.app/Contents/Resources/bin \
  "$HOME/Applications/Docker.app/Contents/Resources/bin" "$HOME/.docker/bin"; do
  export PATH="$PATH:$bin_dir"
done

resolve_python313() {
  local candidate
  for candidate in python3.13 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 13))' >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

ensure_brew() {
  if ! command -v brew >/dev/null 2>&1; then
    echo "[install] Homebrew"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
  assert_command brew Homebrew
}

ensure_tool() {
  local package="$1" tool="$2" kind="$3"
  if [[ "$package" == python@3.13 ]]; then
    if python313="$(resolve_python313)"; then
      echo "[ok] Python 3.13 ($python313)"
      return
    fi
  elif command -v "$tool" >/dev/null 2>&1; then
    echo "[ok] $package ($(command -v "$tool"))"
    return
  fi
  # An existing app with a missing CLI needs repair, never a second installation.
  local app=""
  case "$package" in
    docker-desktop) app="Docker.app" ;;
    visual-studio-code) app="Visual Studio Code.app" ;;
  esac
  if [[ -n "$app" ]] && { [[ -d "/Applications/$app" ]] || [[ -d "$HOME/Applications/$app" ]]; }; then
    echo "$app is installed but its CLI is unavailable. Repair the app's CLI and rerun." >&2
    exit 1
  fi
  if [[ "$skip_tool_install" == true ]]; then
    echo "$package is missing and --skip-tool-install was supplied." >&2
    exit 1
  fi
  ensure_brew
  if brew list "--$kind" "$package" >/dev/null 2>&1; then
    echo "$package is already installed with Homebrew but its required CLI is unavailable. Repair PATH and rerun." >&2
    exit 1
  fi
  if [[ "$package" == powershell ]] && brew tap | grep -qx "powershell/tap"; then
    echo "[migrate] Archived PowerShell Homebrew tap"
    brew untap --force powershell/tap
  fi
  echo "[install] $package"
  HOMEBREW_NO_INSTALL_UPGRADE=1 brew install "--$kind" "$package"
  if [[ "$package" == python@3.13 ]]; then
    python313="$(resolve_python313)" || { echo "Python 3.13 could not be resolved." >&2; exit 1; }
  else
    assert_command "$tool" "$package"
  fi
}

ensure_tool azure-cli az formula
ensure_tool gh gh formula
ensure_tool git git formula
ensure_tool node node formula
ensure_tool powershell pwsh formula
ensure_tool python@3.13 python3.13 formula
ensure_tool docker-desktop docker cask
ensure_tool visual-studio-code code cask
assert_command npm npm

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
    if [[ -x "$python_path" ]] && [[ "$("$python_path" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.13" ]]; then
      rm -rf "$checkout_root/.venv"
    fi
    if [[ ! -x "$python_path" ]]; then
      "$python313" -m venv "$checkout_root/.venv"
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
