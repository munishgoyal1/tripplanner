# New Windows machine setup

This procedure recreates the Tripplanner development layout after the repository
has been cloned from GitHub. It covers the application toolchain, portable VS
Code and GitHub Copilot configuration, and the persistent three-worker plus one
MasterAgent worktree layout.

## One-click path

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

## What the launcher configures

The full setup performs these operations:

1. Installs missing Git, Node.js LTS, Python 3.13, PowerShell 7, Visual Studio
   Code, Docker Desktop, Azure CLI, and GitHub CLI packages through `winget`.
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
7. Restores `worker-1`, `worker-2`, and `worker-3` from their existing
   `origin/agents/worker-*` branches. If a remote slot does not exist, it is
   created from current `origin/master`.
8. Copies the primary `.env` into each new worker, creates each worker's isolated
   `.venv` and frontend dependencies, and verifies its frontend build.
9. Opens four distinct VS Code workspaces: Agent 1 - SmallFixes, Agent 2 -
   UXlabs, Agent 3 - Sandbox, and MasterAgent - Review & Integration.

The workers live beside the clone in `<clone>.worktrees\worker-N`. Workspace
files in the primary checkout provide stable titles, colors, panel placement,
and terminal/editor restoration settings.

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
   approved secret channel, then rerun setup so newly created workers receive it.
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
| Provider and OAuth secrets | `<repo>\.env` | Transfer securely; never commit |
| Local JSON trips/preferences | `%USERPROFILE%\.tripplanner\` | Optional personal data migration |
| UX Lab decisions | `%LOCALAPPDATA%\Tripplanner\ux-labs\selections.json` | Copy to preserve authoritative local Lab lifecycle and handoff history |
| VS Code authentication and chat history | VS Code/GitHub account state | Sign in; session sync may restore supported chat history |
| Azure, GitHub CLI, Docker credentials | Windows credential stores | Authenticate again; do not copy credential databases |
| Cosmos Emulator data | Docker volumes | Start clean unless a deliberate data migration is required |

Repository settings, workspace files, extensions, Copilot instructions, branch
layout, and dependencies are reproducible. Credentials, local product data, open
editors, terminal processes, and machine-local chat state are not guaranteed to
be byte-for-byte portable.

## Verify the environment

Run these checks from the primary checkout:

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

`git worktree list` should show `master` plus `agents/worker-1`,
`agents/worker-2`, and `agents/worker-3`. Reopen all four windows later with:

```powershell
.\Open-Tripplanner-All-Agents.cmd
```

MasterAgent owns local stack startup. Start the application from the primary
checkout with `scripts/user/Run-Latest.cmd`; workers use server-free validation
unless the owner explicitly assigns stack lifecycle work.

## Recovery

- Re-run `Setup-Tripplanner-Dev.cmd` after an interrupted install; completed
  steps are retained.
- VS Code settings backups are timestamped beside
  `%APPDATA%\Code\User\settings.json`.
- If a worker directory exists but is invalid, inspect `git worktree list`
  before removing anything. Do not delete a worktree containing uncommitted or
  unpushed work.
- Use `scripts/user/Sync-AllTo-Latest.cmd` after setup to integrate committed
  lane heads through `master` and synchronize all four worktrees.
