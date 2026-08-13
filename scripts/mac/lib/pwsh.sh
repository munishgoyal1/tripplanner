# Resolve PowerShell without depending on PATH. Sourced by every .command launcher.
#
# The launchers cannot assume `pwsh` is on PATH. A Finder double-click runs with
# a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin), and a terminal inherited from a
# process started inside a `brew` command gets Homebrew's sanitized PATH, which
# replaces the Homebrew bin directory with its shim directory. In both cases
# PowerShell is installed and runnable, but a bare `pwsh` fails to resolve.

resolve_pwsh() {
  if command -v pwsh >/dev/null 2>&1; then
    command -v pwsh
    return 0
  fi
  local candidate
  for candidate in \
    /opt/homebrew/bin/pwsh \
    /usr/local/bin/pwsh \
    /usr/local/microsoft/powershell/7/pwsh; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

# Sets PWSH_BIN, or exits with an actionable message.
require_pwsh() {
  if ! PWSH_BIN="$(resolve_pwsh)"; then
    echo "PowerShell (pwsh) was not found." >&2
    echo "Install it with:  brew install powershell" >&2
    echo "Or run the full setup:  ${TRIPPLANNER_REPO_ROOT:-<repo>}/Setup-Tripplanner-Dev.command" >&2
    exit 1
  fi
  export PWSH_BIN
}
