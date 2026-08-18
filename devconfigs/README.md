# Portable Developer Configurations

This folder stores developer-environment preferences that are safe to carry
between machines. It is intentionally separate from application runtime
configuration and must never contain passwords, tokens, tenant IDs, subscription
IDs, private keys, or machine-specific paths.

## Contents

| Path | Purpose |
| --- | --- |
| `Apply-DevConfigs.ps1` | Merge portable settings into the current Windows or macOS VS Code profile |
| `vscode/settings.json` | Stable VS Code user and layout preferences |
| `vscode/extensions.txt` | Curated, portable VS Code extension IDs |
| `github-copilot/instructions/*.instructions.md` | Global instructions copied to the VS Code prompts folder |
| `windows/packages.psd1` | Optional Windows developer-tool package manifest |
| `macos/Brewfile` | Homebrew developer-tool package manifest |
| `CONFIG-CHANGES.txt` | Plain-English, chronological configuration log |

## Apply on a new machine

For the full application, VS Code/Copilot, and four-agent environment, use the
canonical [new-machine setup guide](../docs/development/new-machine-setup.md) or
run `scripts\win\Setup-Tripplanner-Dev.cmd` on Windows or `scripts/mac/Setup-Tripplanner-Dev.command` on
macOS from the repository root.

To apply only the portable user configuration, open PowerShell in the repository
root and run:

```powershell
.\devconfigs\Apply-DevConfigs.ps1
```

The default operation:

- backs up an existing VS Code `settings.json`;
- merges only the settings owned by this folder, preserving unrelated settings;
- installs the global GitHub Copilot instruction files; and
- does not install software or copy secrets.

To also install missing tools declared in `windows/packages.psd1` with `winget`:

```powershell
.\devconfigs\Apply-DevConfigs.ps1 -InstallTools
```

To install the curated VS Code extension set:

```powershell
.\devconfigs\Apply-DevConfigs.ps1 -InstallExtensions
```

The switches can be combined. Preview any operation with `-WhatIf`. Re-running
the script is supported.

On macOS, install the declared tools with the root setup launcher or directly:

```bash
brew bundle --file devconfigs/macos/Brewfile
pwsh -File devconfigs/Apply-DevConfigs.ps1 -InstallExtensions
```

## Deliberately manual settings

VS Code restores the last layout of an existing workspace, but it has no stable
user setting that forces every new Copilot chat to open as an editor tab. For a
new workspace, use **Chat: Open Chat in Editor** once; editor restoration then
keeps that placement for later launches.

Chat-session renaming also depends on host support. The portable Copilot
instruction requests a 4-5 word title before work and requires progress updates
to show `Current task: ...` when direct renaming is unavailable.

## Adding configurations

Put each tool in its own subfolder and update this README and
`CONFIG-CHANGES.txt`. Prefer declarative files and idempotent apply logic. Keep
machine-specific values in documented placeholders or local untracked files,
never in this folder.
