"""Multiagent persisted state, lease, and report contracts."""

from __future__ import annotations

from tests.support.multiagent import core


def test_a_slot_is_reserved_until_its_pushed_commit_is_integrated() -> None:
    """Reusing the slot would force-reset the branch holding unintegrated work."""
    state = core.State(assignments=[core.Assignment(issue=42, slot="slot-1", state="pushed")])

    assert state.held_slots() == {"slot-1"}
    assert state.busy_slots() == set()


def test_the_worker_report_is_read_from_its_trailing_block() -> None:
    report = core.parse_worker_report(
        "chatter\n```\nRESULT: done\nCOMMIT: abc123\nFILES: src/a.py\nVALIDATION: pytest ok\n```"
    )

    assert report["RESULT"] == "done"
    assert report["COMMIT"] == "abc123"
    assert report["VALIDATION"] == "pytest ok"


def test_secrets_never_reach_an_issue_or_a_transcript() -> None:
    cleaned = core.redact("token=ghp_abcdefghijklmnopqrstuvwxyz01 and AccountKey=zzz;", ["zzz"])

    assert "ghp_" not in cleaned
    assert "AccountKey=zzz" not in cleaned


def test_a_lease_expires_so_a_crash_cannot_wedge_the_system() -> None:
    live = core.Lease.issue_to("controller", minutes=10, pid=1234)
    stale = core.Lease.issue_to("controller", minutes=-1, pid=1234)

    assert live.valid()
    assert not stale.valid()
    assert not core.Lease().valid()


def test_state_survives_a_round_trip() -> None:
    state = core.State(baseline_sha="a" * 40)
    state.assignments.append(core.Assignment(issue=42, slot="slot-1", state="running", pid=99))

    restored = core.State.from_dict(state.to_dict())

    assert restored.baseline_sha == state.baseline_sha
    assert restored.assignments[0].issue == 42
    assert restored.busy_slots() == {"slot-1"}
