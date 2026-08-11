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