"""Multiagent shipping cadence, integration, coordinator, and launcher contracts."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from tests.support.multiagent import DEV, ROOT, core, integrated, issue, runtime


def test_a_busy_queue_still_publishes_accepted_work() -> None:
    """A continuously refilled queue is never idle, so idleness cannot be the trigger."""
    waiting = [integrated(1), integrated(2), integrated(3)]

    assert core.batch_ship_reason(waiting, active=True)


def test_accepted_work_publishes_once_it_has_waited_long_enough() -> None:
    assert core.batch_ship_reason([integrated(1, minutes_ago=11)], active=True)
    assert core.batch_ship_reason([integrated(1, minutes_ago=5)], active=True) is None


def test_an_idle_controller_still_publishes_a_single_fix() -> None:
    assert core.batch_ship_reason([integrated(1)], active=False)


def test_nothing_accepted_means_nothing_to_publish() -> None:
    assert core.batch_ship_reason([], active=False) is None


def test_controller_publishes_and_refreshes_master_before_dispatch() -> None:
    source = (DEV / "multiagent.py").read_text(encoding="utf-8")
    loop = source[source.index("def cmd_run(") : source.index("def cmd_start(")]

    assert loop.index("integrate(space") < loop.index("finalise_batch(space")
    assert loop.index("finalise_batch(space") < loop.index("refresh_integration_baseline(space")
    assert loop.index("refresh_integration_baseline(space") < loop.index("dispatch(space")


def test_an_unowned_integrating_claim_is_returned_to_the_queue() -> None:
    board = (
        issue(1, core.INTEGRATING),
        issue(2, core.INTEGRATING),
        issue(3, core.BLOCKED, core.DECISION_NEEDED),
    )

    assert core.stale_claims(board, frozenset({2})) == (1,)


def test_an_owner_decision_is_never_swept_away() -> None:
    board = (issue(3, core.BLOCKED, core.DECISION_NEEDED),)

    assert core.stale_claims(board, frozenset()) == ()


def test_coordinator_opens_titled_chat_in_last_active_window(tmp_path, monkeypatch) -> None:
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runtime, "run", run)

    coordinator = tmp_path / "coordinator"
    monkeypatch.setattr(runtime, "sync_coordinator", lambda _space: coordinator)
    space = SimpleNamespace(primary=tmp_path / "primary")
    assert runtime.cmd_coordinator(space, SimpleNamespace()) == 0
    assert len(commands) == 1
    assert commands[0][:5] == ["code", "chat", "-m", "autopilot", "--reuse-window"]
    assert "rename this chat to `Coordinator`" in commands[0][-1]
    assert str(coordinator) in commands[0][-1]
    assert runtime.COORDINATOR_BRANCH in commands[0][-1]
    assert "never directly in primary master" in commands[0][-1]
    assert "Every fix I request in this chat is owned by this coordinator" in commands[0][-1]
    assert "run Publish-Coordinator" in commands[0][-1]


def test_publish_coordinator_merges_and_synchronizes_sandboxes(tmp_path, monkeypatch) -> None:
    primary = tmp_path / "primary"
    coordinator = tmp_path / "coordinator"
    primary.mkdir()
    coordinator.mkdir()
    sync_script = primary / "scripts" / "dev" / "sync-sbxs-from-master.ps1"
    sync_script.parent.mkdir(parents=True)
    sync_script.write_text("", encoding="utf-8")
    commands: list[list[str]] = []

    def git(args: list[str], **_kwargs: object) -> str:
        if args == ["branch", "--show-current"]:
            return "master"
        if args == ["status", "--porcelain"]:
            return ""
        if args == ["rev-parse", "HEAD"]:
            return "abc123"
        if args == ["rev-list", "--count", "origin/master..HEAD"]:
            return "1"
        return ""

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        if args[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(args, 0, "77\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    space = SimpleNamespace(
        primary=primary,
        repo=lambda: "owner/repo",
    )
    monkeypatch.setattr(runtime, "git", git)
    monkeypatch.setattr(runtime, "run", run)
    monkeypatch.setattr(runtime, "sync_coordinator", lambda _space: coordinator)
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: "/usr/bin/pwsh")

    assert runtime.cmd_publish_coordinator(space, SimpleNamespace()) == 0
    assert ["gh", "pr", "merge", "77", "--repo", "owner/repo", "--merge"] in commands
    assert ["/usr/bin/pwsh", "-NoProfile", "-File", str(sync_script)] in commands


def test_merged_assignments_are_reconciled_as_landed(tmp_path, monkeypatch) -> None:
    landed = core.Assignment(state="in-pull-request", pushed_sha="merged-sha")
    pending = core.Assignment(state="in-pull-request", pushed_sha="pending-sha")
    state = core.State(assignments=[landed, pending])

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0 if "merged-sha" in args else 1, "", "")

    monkeypatch.setattr(runtime, "run", run)

    assert runtime.reconcile_landed_assignments(state, tmp_path) == 1
    assert landed.state == "landed"
    assert pending.state == "in-pull-request"


def test_finalised_batch_merges_validated_work_before_dispatch(tmp_path, monkeypatch) -> None:
    assignment = core.Assignment(issue=42, state="integrated", pushed_sha="abc123")
    state = core.State(baseline_sha="pre-reconciliation", assignments=[assignment])
    commands: list[list[str]] = []

    def git(args: list[str], **_kwargs: object) -> str:
        commands.append(args)
        return "validated-head" if args == ["rev-parse", "HEAD"] else ""

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        stdout = "191\n" if args[:3] == ["gh", "pr", "list"] else ""
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(runtime, "ensure_integration", lambda _space: tmp_path)
    monkeypatch.setattr(runtime, "git", git)
    monkeypatch.setattr(runtime, "run", run)
    monkeypatch.setattr(runtime, "validate", lambda *_args, **_kwargs: (True, "passed"))
    monkeypatch.setattr(runtime, "set_agent_state", lambda *_args, **_kwargs: None)

    assert runtime.finalise_batch(SimpleNamespace(), state, "owner/repo")

    assert state.baseline_sha == "validated-head"
    assert ["rev-parse", "HEAD"] in commands
    assert ["gh", "pr", "merge", "191", "--repo", "owner/repo", "--merge"] in commands
    assert assignment.state == "landed"


def test_unmerged_batch_blocks_new_dispatch(tmp_path, monkeypatch) -> None:
    assignment = core.Assignment(issue=42, state="integrated", pushed_sha="abc123")
    state = core.State(baseline_sha="validated-head", assignments=[assignment])

    def git(args: list[str], **_kwargs: object) -> str:
        return "validated-head" if args == ["rev-parse", "HEAD"] else ""

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(args, 0, "191\n", "")
        if args[:3] == ["gh", "pr", "merge"]:
            return subprocess.CompletedProcess(args, 1, "", "checks pending")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(runtime, "ensure_integration", lambda _space: tmp_path)
    monkeypatch.setattr(runtime, "git", git)
    monkeypatch.setattr(runtime, "run", run)
    monkeypatch.setattr(runtime, "validate", lambda *_args, **_kwargs: (True, "passed"))
    monkeypatch.setattr(runtime, "set_agent_state", lambda *_args, **_kwargs: None)

    assert not runtime.finalise_batch(SimpleNamespace(), state, "owner/repo")
    assert assignment.state == "in-pull-request"
    assert "did not merge" in state.last_error


def test_dispatch_baseline_refreshes_and_validates_current_master(tmp_path, monkeypatch) -> None:
    state = core.State(baseline_sha="old-baseline")
    commands: list[list[str]] = []
    saved: list[str] = []

    def git(args: list[str], **_kwargs: object) -> str:
        commands.append(args)
        if args == ["rev-parse", "HEAD"]:
            merged = ["git", "merge", "--no-edit", "origin/master"] in commands
            return "refreshed-head" if merged else "old-head"
        if args == ["rev-parse", "origin/master"]:
            return "new-master"
        return ""

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 1 if "merge-base" in args else 0, "", "")

    monkeypatch.setattr(runtime, "ensure_integration", lambda _space: tmp_path)
    monkeypatch.setattr(runtime, "git", git)
    monkeypatch.setattr(runtime, "run", run)
    monkeypatch.setattr(runtime, "validate", lambda *_args, **_kwargs: (True, "passed"))
    monkeypatch.setattr(runtime, "park_released_slots", lambda *_args: None)
    monkeypatch.setattr(
        runtime,
        "save_state",
        lambda _space, current: saved.append(current.baseline_sha),
    )

    assert runtime.refresh_integration_baseline(SimpleNamespace(), state)
    assert ["git", "merge", "--no-edit", "origin/master"] in commands
    assert state.baseline_sha == "refreshed-head"
    assert saved == ["refreshed-head"]


def test_every_launcher_pair_forwards_the_same_verb() -> None:
    verbs = {
        "Start-Multiagent": "start",
        "Stop-Multiagent": "stop",
        "Pause-Multiagent": "pause",
        "Resume-Multiagent": "resume",
        "Multiagent-Prune": "prune",
        "Multiagent-Status": "status",
        "Plan-Multiagent": "plan",
        "Open-Coordinator": "coordinator",
        "Publish-Coordinator": "publish-coordinator",
        "Run-Quality-Issue-Producer": "audit",
    }
    for name, verb in verbs.items():
        windows = (
            ROOT / "scripts" / "win" / "user" / "multiagent" / f"{name}.cmd"
        ).read_text(encoding="utf-8")
        mac = (
            ROOT / "scripts" / "mac" / "user" / "multiagent" / f"{name}.command"
        ).read_text(encoding="utf-8")
        assert f'multiagent.ps1" {verb}' in windows, name
        assert f'multiagent.ps1" {verb} ' in mac, name


def test_the_dispatcher_reuses_the_primary_virtual_environment() -> None:
    dispatcher = (DEV / "multiagent.ps1").read_text(encoding="utf-8")

    assert "--git-common-dir" in dispatcher
    assert "multiagent.py" in dispatcher
