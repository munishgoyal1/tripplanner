"""Multiagent worker dispatch, process supervision, and recovery contracts."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.support.multiagent import assignment, core, issue, runtime


def test_prune_worker_sessions_keeps_only_open_issue_sessions(tmp_path: Path) -> None:
    copilot_home = tmp_path / ".copilot"
    session_root = copilot_home / "session-state"
    cache_path = copilot_home / "vscode.session.metadata.cache.json"
    for session_id in ("open-session", "closed-session", "unowned-session"):
        (session_root / session_id).mkdir(parents=True)
    cache_path.write_text(json.dumps({
        "open-session": {"origin": "other"},
        "closed-session": {"origin": "other"},
        "unowned-session": {"origin": "other"},
    }), encoding="utf-8")

    candidates = runtime.prune_worker_sessions(
        [
            assignment(86, "open-session"),
            assignment(65, "closed-session"),
            assignment(66, "already-absent"),
        ],
        {86},
        copilot_home=copilot_home,
        dry_run=False,
    )

    assert [item.issue for item in candidates] == [65]
    assert (session_root / "open-session").exists()
    assert not (session_root / "closed-session").exists()
    assert (session_root / "unowned-session").exists()
    assert set(json.loads(cache_path.read_text(encoding="utf-8"))) == {
        "open-session", "unowned-session",
    }


def test_prune_worker_sessions_dry_run_changes_nothing(tmp_path: Path) -> None:
    copilot_home = tmp_path / ".copilot"
    session_path = copilot_home / "session-state" / "closed-session"
    session_path.mkdir(parents=True)
    cache_path = copilot_home / "vscode.session.metadata.cache.json"
    cache_path.write_text('{"closed-session": {}}\n', encoding="utf-8")

    candidates = runtime.prune_worker_sessions(
        [assignment(65, "closed-session")],
        set(),
        copilot_home=copilot_home,
        dry_run=True,
    )

    assert [item.issue for item in candidates] == [65]
    assert session_path.exists()
    assert "closed-session" in json.loads(cache_path.read_text(encoding="utf-8"))


def test_every_worker_launch_pins_gpt_56_sol_medium(tmp_path, monkeypatch) -> None:
    commands: list[list[str]] = []

    class Process:
        pid = 123

    def popen(command: list[str], **_kwargs: object) -> Process:
        commands.append(command)
        return Process()

    space = SimpleNamespace(
        transcripts=tmp_path / "transcripts",
        runtime=tmp_path / "runtime",
        slot_path=lambda _slot: tmp_path,
    )
    space.transcripts.mkdir()
    monkeypatch.setattr(runtime.subprocess, "Popen", popen)

    runtime.launch_worker(
        space,
        issue(42, core.READY),
        slot="slot-1",
        branch="multiagent/issue-42-attempt-1",
        attempt=1,
        base_sha="a" * 40,
        repo="owner/repo",
        answer="",
    )

    command = commands[0]
    assert command[command.index("--model") + 1] == runtime.WORKER_MODEL == "gpt-5.6-sol"
    assert (
        command[command.index("--reasoning-effort") + 1]
        == runtime.WORKER_REASONING_EFFORT
        == "medium"
    )
    assert "auto" not in (argument.lower() for argument in command)
    assert not any("claude" in argument.lower() for argument in command)
    assert command[command.index("--name") + 1] == "Slot 1 | #42 t"
    assert "--autopilot" in command
    assert "--allow-all" in command
    assert "--remote-export" in command
    assert "--allow-all-tools" not in command


def test_dispatch_resets_the_reusable_slot_branch_before_launch(tmp_path, monkeypatch) -> None:
    events: list[tuple[str, list[str] | str]] = []
    prior = core.Assignment(issue=42, attempt=2, slot="slot-2", state="in-pull-request")
    state = core.State(baseline_sha="a" * 40, assignments=[prior])
    candidate = issue(42, core.READY)

    monkeypatch.setattr(runtime, "gh_issues", lambda *_args, **_kwargs: [candidate])
    monkeypatch.setattr(runtime, "ensure_slot", lambda *_args: tmp_path)
    monkeypatch.setattr(runtime, "save_state", lambda *_args: None)
    monkeypatch.setattr(runtime, "set_agent_state", lambda *_args, **_kwargs: None)

    def git(args: list[str], **_kwargs: object) -> str:
        events.append(("git", args))
        return ""

    def launch(*_args: object, branch: str, **_kwargs: object) -> tuple[int, str, Path]:
        events.append(("launch", branch))
        return 123, "session", tmp_path / "worker.log"

    monkeypatch.setattr(runtime, "git", git)
    monkeypatch.setattr(runtime, "launch_worker", launch)

    runtime.dispatch(SimpleNamespace(), state, "owner/repo")

    branch = "multiagent/slot-1"
    publish = events.index(
        ("git", ["push", "-q", "--force-with-lease", "-u", "origin", branch])
    )
    launched = events.index(("launch", branch))
    assert publish < launched
    assert state.assignments[-1].branch == branch
    assert state.assignments[-1].attempt == 3


def test_released_slot_parks_on_a_current_tracked_branch(tmp_path, monkeypatch) -> None:
    commands: list[list[str]] = []
    state = core.State(baseline_sha="a" * 40)
    monkeypatch.setattr(runtime, "ensure_slot", lambda *_args: tmp_path)

    def git(args: list[str], **_kwargs: object) -> str:
        commands.append(args)
        return ""

    monkeypatch.setattr(runtime, "git", git)

    assert runtime.park_slot(SimpleNamespace(), state, "slot-2")
    assert ["checkout", "-B", "multiagent/slot-2", "a" * 40] in commands
    assert [
        "push", "-q", "--force-with-lease", "-u", "origin", "multiagent/slot-2",
    ] in commands


def test_worker_session_name_is_concise() -> None:
    named_issue = issue(72, core.READY, title="Make multiagent shutdown bounded and reliable")

    name = runtime.worker_session_name(named_issue, "slot-2")

    assert name.startswith("Slot 2 | #72 Make multiagent shutdown")
    assert len(name) <= 59


def test_preflight_finds_copilot_without_launching_it(tmp_path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    primary = tmp_path / "primary"
    (primary / ".venv").mkdir(parents=True)
    monkeypatch.setattr(runtime, "run", run)
    monkeypatch.setattr(runtime.shutil, "which", lambda tool: f"/bin/{tool}")

    assert runtime.preflight(SimpleNamespace(primary=primary)) == []
    assert ["copilot", "--version"] not in calls
    assert all(command[0] != "copilot" for command in calls)


@pytest.mark.skipif(os.name == "nt", reason="POSIX child reaping only")
def test_exited_worker_child_is_reaped_without_remaining_running() -> None:
    process = subprocess.Popen(  # noqa: S603 - fixed interpreter and inline test program
        [sys.executable, "-c", "print('finished')"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert process.stdout
    assert process.stdout.read() == "finished\n"

    assert not runtime.worker_running(process.pid)
    with pytest.raises(ChildProcessError):
        os.waitpid(process.pid, os.WNOHANG)
    process.returncode = 0


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups only")
def test_stop_owned_process_forces_the_complete_process_group(tmp_path) -> None:
    child_pid_path = tmp_path / "child.pid"
    marker = "multiagent-stop-test"
    program = (
        "import signal, subprocess, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)']); "
        "open(sys.argv[1], 'w').write(str(child.pid)); time.sleep(60)"
    )
    process = subprocess.Popen(  # noqa: S603 - fixed interpreter and test program
        [sys.executable, "-c", program, str(child_pid_path), marker],
        start_new_session=True,
    )
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not child_pid_path.exists():
        time.sleep(0.01)
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))

    try:
        assert runtime.stop_owned_process(process.pid, marker) == "forced"
        assert not runtime.owned_process_running(process.pid, marker)
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (PermissionError, ProcessLookupError):
            pass
        process.wait(timeout=2)


def test_stop_is_idempotent_and_reloads_state_after_controller_exit(tmp_path, monkeypatch) -> None:
    assignment = core.Assignment(
        issue=72,
        slot="slot-1",
        state="running",
        pid=222,
        session_id="worker-session",
    )
    initial = core.State(
        lease=core.Lease(holder="controller", pid=111),
        assignments=[assignment],
    )
    saved: list[core.State] = []
    calls: list[tuple[int, str]] = []
    space = SimpleNamespace(
        controller_pid=tmp_path / "controller.pid",
    )
    space.controller_pid.write_text("333", encoding="utf-8")

    monkeypatch.setattr(runtime, "load_state", lambda _space: initial)
    monkeypatch.setattr(runtime, "save_state", lambda _space, state: saved.append(state))
    monkeypatch.setattr(
        runtime,
        "stop_owned_process",
        lambda pid, marker: calls.append((pid, marker)) or "absent-or-stale",
    )

    assert runtime.cmd_stop(space, SimpleNamespace()) == 0

    assert calls == [
        (111, "multiagent.py run"),
        (333, "multiagent.py run"),
        (222, "worker-session"),
    ]
    assert initial.assignments[0].state == "stopped"
    assert initial.lease.pid == 0
    assert len(saved) == 1
    assert not space.controller_pid.exists()


def test_stop_reports_a_process_tree_that_survives_escalation(tmp_path, monkeypatch) -> None:
    initial = core.State(lease=core.Lease(holder="controller", pid=111))
    space = SimpleNamespace(controller_pid=tmp_path / "missing.pid")
    monkeypatch.setattr(runtime, "load_state", lambda _space: initial)
    monkeypatch.setattr(runtime, "save_state", lambda *_args: None)
    monkeypatch.setattr(runtime, "stop_owned_process", lambda *_args: "failed")

    assert runtime.cmd_stop(space, SimpleNamespace()) == 2


def test_restart_reconciles_a_stopped_assignment_from_its_transcript(
    tmp_path, monkeypatch
) -> None:
    space = SimpleNamespace(transcripts=tmp_path)
    assignment = core.Assignment(
        issue=42,
        attempt=2,
        slot="slot-1",
        state="stopped",
        pid=123,
    )
    state = core.State.from_dict(core.State(assignments=[assignment]).to_dict())
    runtime.transcript_path(space, 42, 2).write_text(
        "RESULT: done\nCOMMIT: abc123\nFILES: scripts/dev/multiagent.py\n"
        "VALIDATION: pytest passed\n",
        encoding="utf-8",
    )
    labels: list[tuple[int, str | None]] = []
    monkeypatch.setattr(
        runtime,
        "set_agent_state",
        lambda _repo, number, wanted: labels.append((number, wanted)),
    )
    monkeypatch.setattr(runtime, "confirm_worker_push", lambda *_args: True)
    monkeypatch.setattr(runtime, "park_slot", lambda *_args: True)

    runtime.collect(space, state, "owner/repo")

    assert state.assignments[0].state == "pushed"
    assert state.assignments[0].pushed_sha == "abc123"
    assert labels == [(42, core.INTEGRATING)]


def test_reportless_worker_recovers_an_issue_referenced_remote_push(
    tmp_path, monkeypatch
) -> None:
    assignment = core.Assignment(
        issue=42,
        attempt=1,
        slot="slot-1",
        branch="multiagent/slot-1",
        base_sha="base-sha",
        state="stopped",
    )
    state = core.State(assignments=[assignment])
    space = SimpleNamespace(transcripts=tmp_path, slot_path=lambda _slot: tmp_path)
    labels: list[tuple[int, str | None]] = []
    monkeypatch.setattr(runtime, "recover_reportless_push", lambda *_args: "pushed-sha")
    monkeypatch.setattr(runtime, "confirm_worker_push", lambda *_args: True)
    monkeypatch.setattr(
        runtime,
        "set_agent_state",
        lambda _repo, number, wanted: labels.append((number, wanted)),
    )

    runtime.collect(space, state, "owner/repo")

    assert assignment.state == "pushed"
    assert assignment.pushed_sha == "pushed-sha"
    assert "integration validation required" in assignment.validation
    assert labels == [(42, core.INTEGRATING)]


def test_reportless_push_requires_matching_issue_trailer(tmp_path, monkeypatch) -> None:
    assignment = core.Assignment(
        issue=42,
        slot="slot-1",
        branch="multiagent/slot-1",
        base_sha="base-sha",
    )
    space = SimpleNamespace(slot_path=lambda _slot: tmp_path)

    monkeypatch.setattr(
        runtime,
        "run",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "", ""),
    )

    def git(args: list[str], **_kwargs: object) -> str:
        if args[0] == "rev-parse":
            return "pushed-sha"
        if args[0] == "show":
            return "A useful commit without an issue trailer"
        return ""

    monkeypatch.setattr(runtime, "git", git)

    assert runtime.recover_reportless_push(space, assignment) == ""


def test_a_blocked_worker_asks_the_owner_on_the_issue(tmp_path, monkeypatch) -> None:
    """A question kept only in controller state would never reach the owner."""
    assignment = core.Assignment(
        issue=42, attempt=1, slot="slot-1", branch="multiagent/slot-1", state="stopped"
    )
    state = core.State(assignments=[assignment])
    space = SimpleNamespace(transcripts=tmp_path, slot_path=lambda _slot: tmp_path)
    runtime.transcript_path(space, 42, 1).write_text(
        "RESULT: blocked\nQUESTION: should Day 2 move, or the place change?\n",
        encoding="utf-8",
    )
    comments: list[tuple[int, str]] = []
    monkeypatch.setattr(runtime, "set_agent_state", lambda *_a, **_k: None)
    monkeypatch.setattr(runtime, "gh_relabel", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runtime, "gh_comment", lambda _repo, number, body: comments.append((number, body))
    )

    runtime.collect(space, state, "owner/repo")

    assert assignment.state == "blocked"
    assert len(comments) == 1
    number, body = comments[0]
    assert number == 42
    assert "should Day 2 move, or the place change?" in body
    assert "owner:decision-needed" in body


def test_status_reports_the_latest_line_of_a_running_worker(tmp_path) -> None:
    assignment = core.Assignment(issue=42, attempt=1, slot="slot-1", state="running")
    space = SimpleNamespace(transcripts=tmp_path)
    runtime.transcript_path(space, 42, 1).write_text(
        "earlier step\n\nreproducing the audit symptom now\n", encoding="utf-8"
    )

    assert runtime.latest_worker_note(space, assignment) == "reproducing the audit symptom now"


def test_a_slow_command_fails_instead_of_killing_the_controller(monkeypatch) -> None:
    """TimeoutExpired escapes the cycle's except clause, so run() must absorb it."""

    def explode(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="slow", timeout=1)

    monkeypatch.setattr(runtime.subprocess, "run", explode)

    result = runtime.run(["slow"], timeout=1)

    assert result.returncode == runtime.TIMEOUT_RETURNCODE
    assert "timed out" in result.stderr


def test_heartbeat_publishes_progress_before_the_cycle_ends(tmp_path) -> None:
    space = SimpleNamespace(state_path=tmp_path / "state.json", ensure_dirs=lambda: None)
    state = core.State(assignments=[core.Assignment(issue=42, state="running")])

    runtime.heartbeat(space, state)

    published = core.State.from_dict(json.loads(space.state_path.read_text(encoding="utf-8")))
    assert [item.issue for item in published.assignments] == [42]
    assert published.lease.valid()


def test_worker_push_is_verified_and_given_remote_tracking(tmp_path, monkeypatch) -> None:
    commands: list[list[str]] = []
    assignment = core.Assignment(
        slot="slot-2",
        branch="multiagent/issue-66-attempt-1",
    )
    space = SimpleNamespace(slot_path=lambda _slot: tmp_path)

    monkeypatch.setattr(
        runtime,
        "run",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0, "", ""),
    )

    def git(args: list[str], **_kwargs: object) -> str:
        commands.append(args)
        return "abc123" if args[0] == "rev-parse" else ""

    monkeypatch.setattr(runtime, "git", git)

    assert runtime.confirm_worker_push(space, assignment, "abc123")
    assert [
        "branch", "--set-upstream-to", "origin/multiagent/issue-66-attempt-1",
        "multiagent/issue-66-attempt-1",
    ] in commands
