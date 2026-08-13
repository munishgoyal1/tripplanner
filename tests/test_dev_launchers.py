from __future__ import annotations

from pathlib import Path


def test_primary_master_launchers_are_named_and_wired_consistently() -> None:
    root = Path(__file__).parents[1]
    run_script = (root / "scripts" / "dev" / "run-latest-master.ps1").read_text(encoding="utf-8")
    mac_launcher = (root / "scripts" / "mac" / "user" / "Run-Latest-Master.command").read_text(
        encoding="utf-8"
    )
    windows_launcher = (root / "scripts" / "user" / "Run-Latest-Master.cmd").read_text(
        encoding="utf-8"
    )

    assert 'branch -ne "master"' in run_script
    assert "fetch -q origin master" in run_script
    assert "merge --ff-only origin/master" in run_script
    assert "run-latest-master.ps1" in mac_launcher
    assert "run-latest-master.ps1" in windows_launcher
    assert not (root / "scripts" / "dev" / "run-latest.ps1").exists()


def test_sync_launcher_defaults_to_all_and_accepts_one_sandbox() -> None:
    root = Path(__file__).parents[1]
    sync_script = (root / "scripts" / "dev" / "sync-latest-from-remote-master.ps1").read_text(
        encoding="utf-8"
    )
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "Sync-Latest-FromRemoteMaster.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "user" / "Sync-Latest-FromRemoteMaster.cmd"
    ).read_text(encoding="utf-8")

    assert '[string]$Sandbox = ""' in sync_script
    assert "fetch -q origin master" in sync_script
    assert "merge --ff-only origin/master" in sync_script
    assert "if ($Sandbox)" in sync_script
    assert "$targets = $registered" in sync_script
    assert "sync-latest-from-remote-master.ps1" in mac_launcher
    assert "sync-latest-from-remote-master.ps1" in windows_launcher
    assert not (root / "scripts" / "dev" / "sync-latest.ps1").exists()
    assert not (root / "scripts" / "dev" / "all-worktrees-sync.ps1").exists()


def test_sync_recovers_pending_conflicts_without_manual_steps() -> None:
    root = Path(__file__).parents[1]
    sync_script = (root / "scripts" / "dev" / "sync-latest-from-remote-master.ps1").read_text(
        encoding="utf-8"
    )

    assert "resolve-sandbox-conflicts.ps1" in sync_script
    # Retry on git state, not on the error text the launcher rewraps.
    assert "--diff-filter=U" in sync_script
    assert "function Test-SandboxConflictPending" in sync_script
    assert "conflicts still need manual resolution" in sync_script
    # One retry only, and only after the conflict is genuinely gone.
    assert sync_script.count("& $resolverScript") == 1


def test_sandbox_scripts_share_one_reference_resolver() -> None:
    root = Path(__file__).parents[1]
    lib = (root / "scripts" / "dev" / "lib" / "sandbox-registry.ps1").read_text(encoding="utf-8")
    resolver = (root / "scripts" / "dev" / "resolve-sandbox-conflicts.ps1").read_text(
        encoding="utf-8"
    )
    sandbox = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")

    assert "function Select-SandboxEntry" in lib
    assert '$Reference -match "^\\d+$"' in lib
    for script in (resolver, sandbox):
        assert "lib/sandbox-registry.ps1" in script
        assert "Select-SandboxEntry" in script
    # The duplicated registry lookup the resolver used to carry is gone.
    assert "([int]$_.slot + 1)" not in resolver
    assert "was not uniquely found" not in resolver


def _merge_block(sandbox_script: str) -> str:
    start = sandbox_script.index('if ($PSCmdlet.ParameterSetName -eq "Merge")')
    end = sandbox_script.index('if ($PSCmdlet.ParameterSetName -eq "Promote")', start)
    return sandbox_script[start:end]


def _code_lines(block: str) -> str:
    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("#"))


def test_merge_lands_sandbox_work_without_discarding_it() -> None:
    root = Path(__file__).parents[1]
    sandbox_script = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")
    block = _merge_block(sandbox_script)
    code = _code_lines(block)

    assert '[Parameter(Mandatory = $true, ParameterSetName = "Merge")]' in sandbox_script
    # Same gates as promotion.
    assert "Invoke-SandboxValidation" in code
    assert "gh pr merge $prNumber --merge" in code
    # The sandbox survives: no discard, no promotion record, no lab state change.
    assert "-Discard" not in code
    assert "Save-SandboxPromotion" not in code
    assert "Write-SandboxLabVersion" not in code
    assert "--delete-branch" not in code
    # The base branch must provably contain the merged commit.
    assert "merge-base --is-ancestor $mergedHead" in code
    # And the sandbox is brought back onto the new base.
    assert code.count("-Update $slug") == 2


def test_merge_launchers_exist_for_both_platforms() -> None:
    root = Path(__file__).parents[1]
    mac_launcher = root / "scripts" / "mac" / "user" / "sandbox" / "Merge-Sandbox.command"
    windows_launcher = root / "scripts" / "user" / "sandbox" / "Merge-Sandbox.cmd"

    assert "sandbox.ps1" in mac_launcher.read_text(encoding="utf-8")
    assert "-Merge" in mac_launcher.read_text(encoding="utf-8")
    assert "-Merge" in windows_launcher.read_text(encoding="utf-8")


def test_github_cli_is_resolved_instead_of_trusting_path() -> None:
    root = Path(__file__).parents[1]
    lib = (root / "scripts" / "dev" / "lib" / "gh-cli.ps1").read_text(encoding="utf-8")
    sandbox_script = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")

    assert "function Resolve-GhCli" in lib
    assert "/opt/homebrew/bin/gh" in lib
    assert "lib/gh-cli.ps1" in sandbox_script
    # A Finder double-click has no Homebrew bin on PATH, so no bare-name lookup
    # may remain in the merge or promote paths.
    assert "& gh " not in sandbox_script
    assert "Get-Command gh " not in sandbox_script
