# New machine setup

This procedure recreates the Tripplanner development layout after the repository
has been cloned from GitHub on Windows or macOS. It covers the application
toolchain, portable VS Code and GitHub Copilot configuration, and sandbox-first
feature development.

## Windows one-click path

1. Clone or populate the repository on the new machine. A short local path such
   as `C:\repos\tripplanner` is recommended because worktrees and Python virtual
   environments create deep paths.
2. From the repository root, double-click `Setup-Tripplanner-Dev.cmd`.
3. Accept any Windows package-install prompts. If a newly installed tool is not
   visible until the process restarts, close the setup window and run the same
   launcher again. The setup is idempotent.
4. Complete the manual sign-ins and secrets in [Manual steps](#manual-steps).

The PowerShell equivalent is:

```powershell
.\scripts\setup-dev-machine.ps1 `
  -FullAgentEnvironment `
  -IncludeMobile `
  -OpenAgentWindows
```

Omit `-OpenAgentWindows` when preparing the machine without opening VS Code.
The existing application-only setup remains available as
`.\scripts\setup-dev-machine.ps1`.

## macOS one-click path

1. Clone the repository to a short local path such as `~/repos/tripplanner`.
2. From Terminal in the repository root, run:

   ```bash
   ./Setup-Tripplanner-Dev.command
   ```

   The file is committed as executable and can also be opened from Finder.
3. Accept any Xcode Command Line Tools or Homebrew prompts. Start Docker Desktop
   when macOS requests approval for its privileged components.
4. Complete the shared manual sign-ins and secrets in
   [Manual steps](#manual-steps).

The script installs the declared `devconfigs/macos/Brewfile`, including Git,
Node.js, Python 3.13, PowerShell 7, VS Code, Docker Desktop, Azure CLI, and GitHub
CLI. Use the underlying script directly for a headless setup:

```bash
./scripts/setup-dev-machine-macos.sh --include-mobile
```

Re-running the setup is supported.

## What the launcher configures

The full setup performs these operations:

1. Installs missing Git, Node.js, Python 3.13, PowerShell 7, Visual Studio Code,
   Docker Desktop, Azure CLI, and GitHub CLI packages through `winget` on Windows
   or Homebrew on macOS.
2. Merges the repository-owned settings from `devconfigs/vscode/settings.json`
   into the current VS Code user settings. Existing settings are backed up and
   unrelated settings are preserved.
3. Installs the curated VS Code extensions, including GitHub Copilot, GitHub
   Copilot Chat, Python/Pylance, PowerShell, ESLint, containers, Azure tools,
   Bicep, and VS Code Speech.
4. Copies the global Copilot instructions from `devconfigs/github-copilot/` into
   the current VS Code prompts folder and installs the GitHub Copilot CLI used
   by automatic merge-conflict recovery.
5. Configures Git `rerere`, automatic recorded-resolution reuse, and `zdiff3`
   conflict context for this repository.
6. Creates `.env` from `.env.example` only when `.env` is absent, then creates
   the Python virtual environment and restores locked Python, frontend, and
   mobile dependencies.
7. Leaves feature isolation to fresh sandboxes created when a task needs one.
   A sandbox copies the primary environment and uses its own worktree, ports,
   and local emulator database.

## Manual steps

Authentication and secrets are deliberately never copied by Git or the setup
script.

1. Open VS Code Accounts, sign into GitHub, and authorize GitHub Copilot. A
   Copilot-enabled GitHub account or organization seat is required.
2. Authenticate the command-line tools:

   ```powershell
   gh auth login
   copilot --version
   ```

3. Fill the primary `.env` with the required provider keys and local settings.
   Never commit it. If migrating from an old machine, transfer it through an
   approved secret channel.
4. Start Docker Desktop before running the local Cosmos emulator or building
   images.
5. Run `az login` only when Azure access is needed. Run `docker login ghcr.io`
   with an appropriate package token only for image publication.
6. In each new workspace, use **Chat: Open Chat in Editor** once if that is the
   preferred placement. VS Code has no stable setting that forces a brand-new
   chat into an editor tab; workspace restoration keeps it there afterward.

## State that does not come from Git

Copy these only when the same local state is genuinely required:

| State | Location | Guidance |
| --- | --- | --- |
| Provider and OAuth secrets | `<repo>/.env` | Transfer securely; never commit |
| Local JSON trips/preferences | Windows: `%USERPROFILE%\.tripplanner\`; macOS: `~/.tripplanner/` | Optional personal data migration |
| UX Lab decisions | Windows: `%LOCALAPPDATA%\Tripplanner\ux-labs\selections.json`; macOS: `~/.tripplanner/Tripplanner/ux-labs/selections.json` | Copy to preserve authoritative local Lab lifecycle and handoff history |
| VS Code authentication and chat history | VS Code/GitHub account state | Sign in; session sync may restore supported chat history |
| Azure, GitHub CLI, Docker credentials | Windows Credential Manager or macOS Keychain | Authenticate again; do not copy credential databases |
| Cosmos Emulator data | Docker volumes | Start clean unless a deliberate data migration is required |

Repository settings, workspace files, extensions, Copilot instructions, branch
layout, and dependencies are reproducible. Credentials, local product data, open
editors, terminal processes, and machine-local chat state are not guaranteed to
be byte-for-byte portable.

## Verify the environment

On Windows, run these checks from the primary checkout:

```powershell
git status --short
git worktree list
code --list-extensions | Select-String "github.copilot|ms-python.python|ms-vscode.powershell"
gh auth status
copilot --version
.\.venv\Scripts\python.exe -c "import fastapi, tripplanner; print('Python OK')"
npm --prefix frontend run build
npm --prefix mobile run typecheck
```

On macOS, run:

```bash
git status --short
git worktree list
code --list-extensions | grep -E "github.copilot|ms-python.python|ms-vscode.powershell"
gh auth status
copilot --version
./.venv/bin/python -c "import fastapi, tripplanner; print('Python OK')"
npm --prefix frontend run build
npm --prefix mobile run typecheck
```

`git worktree list` should show the primary `master` checkout and any currently
active sandboxes. Master owns local stack startup. Start the application from the primary
checkout with `scripts/user/Run-Latest.cmd` on Windows. The macOS setup,
dependency, build/test, and sandbox paths are available, but the full local
`dev-spa.ps1` lifecycle is not yet qualified because Windows-specific process
and npm hooks remain. Use direct Python/npm commands or the hosted canary for
Mac integration testing until that workflow has a passing Mac host smoke.
Sandboxes use server-free validation unless their isolated stack is needed.

## Recovery

- Re-run `Setup-Tripplanner-Dev.cmd` on Windows or
   `Setup-Tripplanner-Dev.command` on macOS after an interrupted install;
   completed steps are retained.
- The macOS setup automatically removes the archived `powershell/tap` before
  installing the current Homebrew Core `powershell` formula. This migration can
  replace an older tap-provided PowerShell installation; rerun the setup after
  any interrupted Homebrew operation.
- Python and npm restores default to public PyPI and npm on Windows, macOS, and
   in container builds. Set `PIP_INDEX_URL` or `NPM_CONFIG_REGISTRY` before
   launching setup only when an environment needs another standards-compatible,
   non-corporate package source. Setup rejects Microsoft corporate package hosts.
- VS Code settings backups are timestamped beside
   `%APPDATA%\Code\User\settings.json` on Windows or
   `~/Library/Application Support/Code/User/settings.json` on macOS.
- If a sandbox directory exists but is invalid, inspect `git worktree list`
   before removing anything. Do not delete a worktree containing uncommitted or
   unpushed work.
- Run `scripts/user/Run-Latest.cmd` from the primary checkout before starting
   the canonical local stack. Use `Update-Sandbox` to bring an in-flight sandbox
   forward from `origin/master`.
