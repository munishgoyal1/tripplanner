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
