"""Coordinate bounded agent workers over owner-approved GitHub issues.

    python scripts/dev/multiagent.py status
    python scripts/dev/multiagent.py plan
    python scripts/dev/multiagent.py start
    python scripts/dev/multiagent.py audit --dry-run

Nothing here dispatches work the owner did not authorise: an issue is only
eligible while it carries the ``owner:ready`` label. The pure selection,
collision, and fingerprint logic lives in ``multiagent_core.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import multiagent_core as core  # noqa: E402

SLOT_COUNT = 2
LEASE_MINUTES = 15
CYCLE_SECONDS = 20
WORKER_TIMEOUT_MINUTES = 60
AUDIT_ISSUE_CAP = 3
INTEGRATION_BRANCH = "multiagent/integration"
TEST_TIMEOUT_SECONDS = 3600
WORKER_MODEL = "gpt-5.6-sol"
WORKER_REASONING_EFFORT = "medium"
STOP_GRACE_SECONDS = 2.0
STOP_KILL_SECONDS = 1.0

_BAR = "-" * 78


def log(message: str) -> None:
    print(message, flush=True)


# ----------------------------------------------------------------------------
# Process and repository plumbing
# ----------------------------------------------------------------------------


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = 600,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def git(args: list[str], *, cwd: Path, check: bool = True) -> str:
    result = run(["git", *args], cwd=cwd)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def primary_root() -> Path:
    here = Path(__file__).resolve().parents[2]
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=here)
    if common.returncode != 0:
        return here
    return Path(common.stdout.strip()).parent


class Workspace:
    """Every path and executable the controller needs, resolved once."""

    def __init__(self) -> None:
        self.primary = primary_root()
        self.root = Path(f"{self.primary}.worktrees") / "multiagent"
        self.runtime = self.root / "runtime"
        self.integration = self.root / "integration"
        self.transcripts = self.runtime / "transcripts"
        self.state_path = self.runtime / "state.json"
        self.controller_pid = self.runtime / "controller.pid"

    def slot_path(self, slot: str) -> Path:
        return self.root / slot

    def ensure_dirs(self) -> None:
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.transcripts.mkdir(parents=True, exist_ok=True)

    def python(self) -> str:
        for candidate in (
            self.primary / ".venv" / "bin" / "python",
            self.primary / ".venv" / "Scripts" / "python.exe",
        ):
            if candidate.exists():
                return str(candidate)
        return sys.executable

    def repo(self) -> str:
        result = run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
        return result.stdout.strip() or "munishgoyal1/tripplanner"


def load_state(space: Workspace) -> core.State:
    if not space.state_path.exists():
        return core.State()
    try:
        return core.State.from_dict(json.loads(space.state_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return core.State()


def save_state(space: Workspace, state: core.State) -> None:
    space.ensure_dirs()
    payload = json.dumps(state.to_dict(), indent=2) + "\n"
    temp = space.state_path.with_suffix(".tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(space.state_path)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, PermissionError):
        return False
    return True


def worker_running(pid: int) -> bool:
    """Return whether a worker is running, reaping owned POSIX children that exited."""
    if os.name == "nt":
        return pid_alive(pid)
    try:
        reaped, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return pid_alive(pid)
    except OSError:
        return False
    return reaped == 0


def process_info(pid: int) -> tuple[str, str]:
    """Return process state and command without treating a stale PID as owned."""
    if pid <= 0:
        return "", ""
    if os.name == "nt":
        script = (
            f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; "
            "if ($p) { $p.CommandLine }"
        )
        result = run(["pwsh", "-NoProfile", "-Command", script], timeout=5)
        return "", result.stdout.strip() if result.returncode == 0 else ""
    result = run(["ps", "-p", str(pid), "-o", "stat=", "-o", "command="], timeout=5)
    if result.returncode != 0 or not result.stdout.strip():
        return "", ""
    state, _, command = result.stdout.strip().partition(" ")
    return state, command.strip()


def owned_process_running(pid: int, marker: str) -> bool:
    state, command = process_info(pid)
    return bool(command and marker in command and not state.startswith("Z"))


def stop_owned_process(pid: int, marker: str) -> str:
    """Stop one owned process tree within a fixed deadline."""
    if not owned_process_running(pid, marker):
        return "absent-or-stale"

    if os.name == "nt":
        run(["taskkill", "/PID", str(pid), "/T"], timeout=5)
    else:
        try:
            process_group = os.getpgid(pid)
        except ProcessLookupError:
            return "absent-or-stale"
        if process_group != pid:
            return "not-group-leader"
        os.killpg(process_group, signal.SIGTERM)

    deadline = time.monotonic() + STOP_GRACE_SECONDS
    while time.monotonic() < deadline and owned_process_running(pid, marker):
        time.sleep(0.05)
    if not owned_process_running(pid, marker):
        return "stopped"

    if os.name == "nt":
        run(["taskkill", "/PID", str(pid), "/T", "/F"], timeout=5)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            return "stopped"

    deadline = time.monotonic() + STOP_KILL_SECONDS
    while time.monotonic() < deadline and owned_process_running(pid, marker):
        time.sleep(0.05)
    return "forced" if not owned_process_running(pid, marker) else "failed"


# ----------------------------------------------------------------------------
# GitHub
# ----------------------------------------------------------------------------


def gh_issues(repo: str, labels: list[str], *, state: str = "open") -> list[core.Issue]:
    args = [
        "gh", "issue", "list", "--repo", repo, "--state", state,
        "--json", "number,title,body,labels,state,updatedAt", "--limit", "60",
    ]
    for label in labels:
        args += ["--label", label]
    result = run(args)
    if result.returncode != 0:
        raise RuntimeError(f"gh issue list failed: {result.stderr.strip()}")
    return [core.Issue.from_api(item) for item in json.loads(result.stdout or "[]")]


def gh_relabel(repo: str, number: int, *, add: list[str] = (), remove: list[str] = ()) -> None:
    args = ["gh", "issue", "edit", str(number), "--repo", repo]
    for label in add:
        args += ["--add-label", label]
    for label in remove:
        args += ["--remove-label", label]
    if len(args) > 6:
        run(args)


def gh_comment(repo: str, number: int, body: str) -> None:
    run(["gh", "issue", "comment", str(number), "--repo", repo, "--body", core.redact(body)])


def set_agent_state(repo: str, number: int, wanted: str | None, *, lane: str = "") -> None:
    """Agent labels are a state, so the previous one always comes off."""
    remove = [label for label in core.AGENT_STATES if label != wanted]
    add = [wanted] if wanted else []
    if lane:
        add.append(lane)
    gh_relabel(repo, number, add=add, remove=remove)


# ----------------------------------------------------------------------------
# Worktrees
# ----------------------------------------------------------------------------


def worktree_exists(space: Workspace, path: Path) -> bool:
    if not path.exists():
        return False
    listed = git(["worktree", "list", "--porcelain"], cwd=space.primary, check=False)
    target = str(path.resolve()).replace("\\", "/")
    return any(line.strip() == f"worktree {target}" for line in listed.splitlines())


def ensure_integration(space: Workspace) -> Path:
    if worktree_exists(space, space.integration):
        return space.integration
    space.root.mkdir(parents=True, exist_ok=True)
    git(["fetch", "-q", "origin", "master"], cwd=space.primary)
    git(
        ["worktree", "add", "-B", INTEGRATION_BRANCH, str(space.integration), "origin/master"],
        cwd=space.primary,
    )
    return space.integration


def ensure_slot(space: Workspace, slot: str) -> Path:
    path = space.slot_path(slot)
    if worktree_exists(space, path):
        return path
    space.root.mkdir(parents=True, exist_ok=True)
    git(["fetch", "-q", "origin", "master"], cwd=space.primary)
    git(["worktree", "add", "--detach", str(path), "origin/master"], cwd=space.primary)
    return path


def remote_multiagent_branches(space: Workspace) -> list[str]:
    listed = git(
        ["ls-remote", "--heads", "origin", f"{core.BRANCH_PREFIX}*"],
        cwd=space.primary,
        check=False,
    )
    return [line.split("refs/heads/")[-1] for line in listed.splitlines() if "refs/heads/" in line]


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------


def touched_frontend(files: str) -> bool:
    return "frontend/" in files or "packages/" in files


def validate(space: Workspace, worktree: Path, *, frontend: bool) -> tuple[bool, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(worktree / "src")
    env["TRIPPLANNER_DEBUG_STORE"] = "0"
    backend = run(
        [space.python(), "-m", "pytest", "-q"],
        cwd=worktree,
        env=env,
        timeout=TEST_TIMEOUT_SECONDS,
    )
    tail = (backend.stdout or backend.stderr).strip().splitlines()
    summary = tail[-1] if tail else "no output"
    if backend.returncode != 0:
        return False, f"pytest failed: {summary}"
    report = f"pytest: {summary}"

    if not frontend:
        return True, report + "; frontend untouched"
    node_modules = worktree / "frontend" / "node_modules"
    if not node_modules.exists():
        install = run(
            ["npm", "install", "--no-audit", "--no-fund"],
            cwd=worktree / "frontend",
            timeout=TEST_TIMEOUT_SECONDS,
        )
        if install.returncode != 0:
            return False, report + "; frontend dependencies would not install"
    web = run(
        ["npm", "test", "--silent"],
        cwd=worktree / "frontend",
        timeout=TEST_TIMEOUT_SECONDS,
    )
    lines = (web.stdout or web.stderr).strip().splitlines()
    web_summary = next((line for line in reversed(lines) if "Tests" in line), lines[-1:] or [""])[0]
    if web.returncode != 0:
        return False, report + f"; frontend failed: {web_summary}"
    return True, report + f"; frontend: {web_summary}"


# ----------------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------------


def transcript_path(space: Workspace, issue_number: int, attempt: int) -> Path:
    return space.transcripts / f"issue-{issue_number}-attempt-{attempt}.log"


def worker_session_name(issue: core.Issue, slot: str) -> str:
    slot_number = slot.rsplit("-", 1)[-1]
    title = " ".join(issue.title.split())
    if len(title) > 44:
        title = title[:41].rstrip() + "..."
    return f"Slot {slot_number} | #{issue.number} {title}"


def launch_worker(
    space: Workspace,
    issue: core.Issue,
    *,
    slot: str,
    branch: str,
    attempt: int,
    base_sha: str,
    repo: str,
    answer: str,
) -> tuple[int, str, Path]:
    """Start one non-interactive Copilot worker, detached, and record where."""
    session_id = str(uuid.uuid4())
    prompt = core.worker_prompt(
        issue, slot=slot, branch=branch, base_sha=base_sha, repo=repo, answer=answer
    )
    transcript = transcript_path(space, issue.number, attempt)
    prompt_path = space.transcripts / f"issue-{issue.number}-attempt-{attempt}-prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    command = [
        "copilot",
        "--model", WORKER_MODEL,
        "--reasoning-effort", WORKER_REASONING_EFFORT,
        "--name", worker_session_name(issue, slot),
        "--prompt", prompt,
        "--allow-all-tools",
        "--no-ask-user",
        "--no-color",
        "--silent",
        "--session-id", session_id,
        "--log-dir", str(space.runtime / "copilot-logs"),
    ]
    handle = transcript.open("w", encoding="utf-8")
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        command,
        cwd=str(space.slot_path(slot)),
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    return process.pid, session_id, transcript


def dispatch(space: Workspace, state: core.State, repo: str) -> None:
    free = [f"slot-{index}" for index in range(1, SLOT_COUNT + 1)]
    busy = state.busy_slots()
    free = [slot for slot in free if slot not in busy]
    if not free:
        return

    issues = gh_issues(repo, [core.READY])
    busy: list[core.Footprint] = []
    for assignment in state.active():
        issue = next((item for item in issues if item.number == assignment.issue), None)
        if issue:
            busy.append(core.issue_footprint(issue))

    plan = core.plan_dispatch(issues, capacity=len(free), busy=tuple(busy))
    branches = remote_multiagent_branches(space)

    for issue, slot in zip(plan.dispatch, free, strict=False):
        attempt = core.next_attempt(branches, issue.number)
        branch = core.branch_name(issue.number, attempt)
        path = ensure_slot(space, slot)
        git(["fetch", "-q", "origin"], cwd=path)
        git(["reset", "--hard"], cwd=path, check=False)
        git(["clean", "-fd"], cwd=path, check=False)
        git(["checkout", "-B", branch, state.baseline_sha], cwd=path)

        answer = ""
        pid, session_id, transcript = launch_worker(
            space, issue, slot=slot, branch=branch, attempt=attempt,
            base_sha=state.baseline_sha, repo=repo, answer=answer,
        )
        state.assignments.append(
            core.Assignment(
                issue=issue.number,
                attempt=attempt,
                slot=slot,
                branch=branch,
                base_sha=state.baseline_sha,
                session_id=session_id,
                pid=pid,
                state="running",
                started=core.format_time(core.utcnow()),
                heartbeat=core.format_time(core.utcnow()),
            )
        )
        if issue.number not in state.batch:
            state.batch.append(issue.number)
        save_state(space, state)
        set_agent_state(repo, issue.number, core.IN_PROGRESS, lane=f"lane:mw-{slot[-1]}")
        log(f"dispatched #{issue.number} to {slot} on {branch} (pid {pid}, log {transcript.name})")


# ----------------------------------------------------------------------------
# Collection and integration
# ----------------------------------------------------------------------------


def collect(space: Workspace, state: core.State, repo: str) -> None:
    stopped = [item for item in state.assignments if item.state == "stopped"]
    for assignment in [*state.active(), *stopped]:
        if assignment.state != "stopped" and worker_running(assignment.pid):
            started = core.parse_time(assignment.started) or core.utcnow()
            if core.utcnow() - started > timedelta(minutes=WORKER_TIMEOUT_MINUTES):
                os.kill(assignment.pid, 15)
                assignment.state = "timeout"
                assignment.finished = core.format_time(core.utcnow())
                set_agent_state(repo, assignment.issue, core.BLOCKED)
                gh_relabel(repo, assignment.issue, add=[core.DECISION_NEEDED])
                gh_comment(
                    repo, assignment.issue,
                    "## Owner Decision\n\n**Question:** this attempt ran past its time budget"
                    f" ({WORKER_TIMEOUT_MINUTES} minutes). Split it, or let it run longer?\n"
                    f"**Why it blocks:** the worker was stopped on `{assignment.branch}`, which"
                    " is kept for inspection.\n**Answer:** waiting",
                )
            continue

        transcript = transcript_path(space, assignment.issue, assignment.attempt)
        text = ""
        if transcript.exists():
            text = transcript.read_text(encoding="utf-8", errors="replace")
        report = core.parse_worker_report(text)
        outcome = (report.get("RESULT") or "failed").lower()
        assignment.finished = core.format_time(core.utcnow())
        assignment.validation = report.get("VALIDATION", "")

        if outcome == "done" and report.get("COMMIT", "none") not in ("", "none"):
            assignment.pushed_sha = report["COMMIT"]
            assignment.state = "pushed"
            set_agent_state(repo, assignment.issue, core.INTEGRATING)
            log(f"#{assignment.issue} reported done at {assignment.pushed_sha[:12]}")
        elif outcome == "blocked":
            assignment.state = "blocked"
            assignment.question = report.get("QUESTION", "")
            set_agent_state(repo, assignment.issue, core.BLOCKED)
            gh_relabel(repo, assignment.issue, add=[core.DECISION_NEEDED])
            log(f"#{assignment.issue} is blocked on an owner decision")
        else:
            assignment.state = "failed"
            set_agent_state(repo, assignment.issue, core.BLOCKED)
            gh_relabel(repo, assignment.issue, add=[core.DECISION_NEEDED])
            gh_comment(
                repo, assignment.issue,
                f"Attempt {assignment.attempt} in `{assignment.slot}` did not finish. Its branch"
                f" `{assignment.branch}` and transcript are kept for inspection.",
            )
            log(f"#{assignment.issue} failed; see {transcript.name}")


def integrate(space: Workspace, state: core.State, repo: str) -> None:
    ready = [item for item in state.assignments if item.state == "pushed"]
    if not ready:
        return
    worktree = ensure_integration(space)
    git(["fetch", "-q", "origin"], cwd=worktree)

    for assignment in ready:
        merged = run(
            ["git", "merge", "--no-ff", "-m",
             f"Integrate #{assignment.issue} attempt {assignment.attempt}", assignment.pushed_sha],
            cwd=worktree,
        )
        if merged.returncode != 0:
            git(["merge", "--abort"], cwd=worktree, check=False)
            assignment.state = "conflicted"
            set_agent_state(repo, assignment.issue, None)
            gh_comment(
                repo, assignment.issue,
                f"Integration of `{assignment.pushed_sha[:12]}` conflicted with the accepted"
                " baseline. Re-queued for a fresh attempt from the newer baseline.",
            )
            log(f"#{assignment.issue} conflicted during integration; re-queued")
            continue

        passed, summary = validate(
            space, worktree, frontend=touched_frontend(assignment.validation)
        )
        if not passed:
            git(["reset", "--hard", state.baseline_sha or "HEAD~1"], cwd=worktree, check=False)
            assignment.state = "rejected"
            assignment.validation = summary
            set_agent_state(repo, assignment.issue, None)
            gh_comment(
                repo, assignment.issue,
                f"Integration validation failed and the baseline was not advanced: {summary}",
            )
            log(f"#{assignment.issue} rejected: {summary}")
            continue

        state.baseline_sha = git(["rev-parse", "HEAD"], cwd=worktree)
        assignment.state = "integrated"
        assignment.validation = summary
        log(f"#{assignment.issue} integrated; baseline now {state.baseline_sha[:12]}")


def finalise_batch(space: Workspace, state: core.State, repo: str) -> None:
    """Re-sync with master, validate the whole batch, and open one PR."""
    integrated = [item for item in state.assignments if item.state == "integrated"]
    if not integrated or state.active():
        return
    worktree = ensure_integration(space)
    git(["fetch", "-q", "origin", "master"], cwd=worktree)

    merged = run(["git", "merge", "--no-edit", "origin/master"], cwd=worktree)
    if merged.returncode != 0:
        git(["merge", "--abort"], cwd=worktree, check=False)
        state.last_error = "integration branch conflicts with origin/master"
        log("batch cannot be finalised: conflicts with origin/master")
        return

    passed, summary = validate(space, worktree, frontend=True)
    if not passed:
        state.last_error = f"aggregate validation failed: {summary}"
        log(state.last_error)
        return

    state.baseline_sha = git(["rev-parse", "HEAD"], cwd=worktree)
    git(["push", "-q", "-u", "origin", INTEGRATION_BRANCH], cwd=worktree)
    closes = "\n".join(f"Fixes #{item.issue}" for item in integrated)
    body = (
        "Batch produced by the multiagent coordinator.\n\n"
        f"Aggregate validation: {summary}\n\n"
        "Merge, do not squash: each worker commit carries its own `Fixes #` trailer.\n\n"
        f"{closes}\n"
    )
    created = run([
        "gh", "pr", "create", "--repo", repo, "--base", "master", "--head", INTEGRATION_BRANCH,
        "--title", f"Multiagent batch: {len(integrated)} issue(s)", "--body", body,
    ])
    if created.returncode != 0 and "already exists" not in created.stderr:
        state.last_error = f"pull request not created: {created.stderr.strip()}"
        log(state.last_error)
        return

    for item in integrated:
        item.state = "in-pull-request"
        set_agent_state(repo, item.issue, core.NEEDS_VERIFY)
    state.batch = []
    log(f"opened the batch pull request with {len(integrated)} issue(s)")


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------


def preflight(space: Workspace) -> list[str]:
    problems: list[str] = []
    for tool in ("git", "gh"):
        if run([tool, "--version"], timeout=60).returncode != 0:
            problems.append(f"{tool} is not available on PATH")
    if shutil.which("copilot") is None:
        problems.append("copilot is not available on PATH")
    if run(["gh", "auth", "status"], timeout=60).returncode != 0:
        problems.append("gh is not authenticated; run: gh auth login")
    if not (space.primary / ".venv").exists():
        problems.append(f"no virtual environment at {space.primary}/.venv")
    return problems


def cmd_status(space: Workspace, args: argparse.Namespace) -> int:
    state = load_state(space)
    repo = space.repo()
    holder = state.lease.holder or "nobody"
    alive = pid_alive(state.lease.pid)
    log(f"Controller     {holder} ({'running' if alive else 'not running'})")
    log(f"Lease valid    {state.lease.valid()} (expires {state.lease.expires or 'n/a'})")
    dispatching = f"paused: {state.paused_reason or 'by owner'}" if state.paused else "on"
    log(f"Dispatching    {dispatching}")
    log(f"Baseline       {state.baseline_sha[:12] or 'not established'}")
    log(f"Worktrees      {space.root}")
    if state.last_error:
        log(f"Last error     {state.last_error}")
    log(_BAR)
    if not state.assignments:
        log("No assignments yet.")
    for item in state.assignments[-12:]:
        log(
            f"  #{item.issue:<5} {item.slot:<7} attempt {item.attempt}  {item.state:<16}"
            f" {item.pushed_sha[:12] or '-'}"
        )
    log(_BAR)
    try:
        waiting = gh_issues(repo, [core.DECISION_NEEDED])
        ready = gh_issues(repo, [core.READY])
    except RuntimeError as error:
        log(f"GitHub unavailable: {error}")
        return 1
    log(f"Waiting on you: {len(waiting)} issue(s)")
    for issue in waiting:
        log(f"  #{issue.number} {issue.title[:60]}")
    log(f"Authorised and open: {len(ready)} issue(s)")
    log(_BAR)
    log("Recovery: Stop-Multiagent, then Start-Multiagent. Worktrees and branches are kept.")
    return 0


def cmd_plan(space: Workspace, args: argparse.Namespace) -> int:
    state = load_state(space)
    repo = space.repo()
    issues = gh_issues(repo, [core.READY])
    if not issues:
        log(f"Nothing carries {core.READY}. Add it to an issue to authorise implementation.")
        return 0
    capacity = SLOT_COUNT - len(state.busy_slots())
    plan = core.plan_dispatch(issues, capacity=capacity)
    log(f"{len(issues)} authorised issue(s); {capacity} free slot(s).")
    log(_BAR)
    for issue in plan.dispatch:
        paths = ", ".join(core.declared_paths(issue.body)[:3]) or "no declared paths"
        log(f"  dispatch  #{issue.number} {issue.title[:52]}")
        log(f"            {paths}")
    for issue, reason in plan.deferred:
        log(f"  hold      #{issue.number} {issue.title[:52]}")
        log(f"            {reason}")
    log(_BAR)
    log("Dry run: no branch, worktree, agent, or label was touched.")
    return 0


def cmd_run(space: Workspace, args: argparse.Namespace) -> int:
    """The controller loop. Started detached by `start`."""
    space.ensure_dirs()
    repo = space.repo()
    state = load_state(space)
    state.lease = core.Lease.issue_to("controller", minutes=LEASE_MINUTES, pid=os.getpid())
    if not state.baseline_sha:
        worktree = ensure_integration(space)
        git(["fetch", "-q", "origin", "master"], cwd=worktree)
        git(["reset", "--hard", "origin/master"], cwd=worktree)
        state.baseline_sha = git(["rev-parse", "HEAD"], cwd=worktree)
    save_state(space, state)
    log(f"controller {os.getpid()} started; baseline {state.baseline_sha[:12]}")

    while True:
        try:
            state = load_state(space)
            if state.lease.pid and state.lease.pid != os.getpid() and pid_alive(state.lease.pid):
                log("another controller holds the lease; exiting")
                return 0
            state.lease = core.Lease.issue_to("controller", minutes=LEASE_MINUTES, pid=os.getpid())
            collect(space, state, repo)
            integrate(space, state, repo)
            if not state.paused:
                dispatch(space, state, repo)
            finalise_batch(space, state, repo)
            state.last_cycle = core.format_time(core.utcnow())
            save_state(space, state)
        except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as error:
            state = load_state(space)
            state.last_error = str(error)[:400]
            save_state(space, state)
            log(f"cycle error: {error}")
        time.sleep(max(5, args.interval))


def cmd_start(space: Workspace, args: argparse.Namespace) -> int:
    space.ensure_dirs()
    problems = preflight(space)
    if problems:
        for problem in problems:
            log(f"blocked: {problem}")
        return 2
    state = load_state(space)
    if state.lease.valid() and pid_alive(state.lease.pid) and not args.force:
        log(f"A controller is already running (pid {state.lease.pid}). Use Stop first.")
        return 1

    ensure_integration(space)
    for index in range(1, SLOT_COUNT + 1):
        ensure_slot(space, f"slot-{index}")

    command = [
        space.python(),
        str(Path(__file__).resolve()),
        "run",
        "--interval",
        str(args.interval),
    ]
    handle = (space.runtime / "controller.log").open("a", encoding="utf-8")
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        command,
        cwd=str(space.primary),
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    space.controller_pid.write_text(str(process.pid), encoding="utf-8")
    log(f"Controller started (pid {process.pid}).")
    log(f"  worktrees  {space.root}")
    log(f"  log        {space.runtime / 'controller.log'}")
    log("  dispatch   only issues carrying owner:ready")
    if not args.no_chat:
        cmd_coordinator(space, args)
    return 0


def cmd_stop(space: Workspace, args: argparse.Namespace) -> int:
    state = load_state(space)
    controller_pids = {state.lease.pid}
    if space.controller_pid.exists():
        try:
            controller_pids.add(int(space.controller_pid.read_text(encoding="utf-8").strip()))
        except ValueError:
            pass
    controller_results = {
        pid: stop_owned_process(pid, "multiagent.py run")
        for pid in sorted(controller_pids)
        if pid > 0
    }

    # The controller is the only other state writer. Reload after it is gone so
    # a final cycle cannot restore its lease or overwrite stopped assignments.
    state = load_state(space)
    stopped = 0
    forced = 0
    failures = sum(
        result in ("failed", "not-group-leader") for result in controller_results.values()
    )
    for assignment in state.active():
        result = stop_owned_process(assignment.pid, assignment.session_id)
        if result in ("stopped", "forced"):
            stopped += 1
        if result == "forced":
            forced += 1
        if result in ("failed", "not-group-leader"):
            failures += 1
        else:
            assignment.state = "stopped"
    state.lease = core.Lease()
    save_state(space, state)
    if space.controller_pid.exists():
        space.controller_pid.unlink()
    controller_summary = ", ".join(
        f"{pid}={result}" for pid, result in sorted(controller_results.items())
    ) or "not running"
    log(f"Controller: {controller_summary}. Workers stopped: {stopped} ({forced} forced).")
    log("Worktrees, branches, and transcripts were kept for inspection.")
    if failures:
        log(f"Shutdown incomplete: {failures} owned process tree(s) survived escalation.")
        return 2
    return 0


def cmd_pause(space: Workspace, args: argparse.Namespace) -> int:
    state = load_state(space)
    state.paused = True
    state.paused_reason = args.reason or "by owner"
    save_state(space, state)
    log("Dispatching paused. Running workers finish; nothing new starts.")
    return 0


def cmd_resume(space: Workspace, args: argparse.Namespace) -> int:
    state = load_state(space)
    state.paused = False
    state.paused_reason = ""
    save_state(space, state)
    log("Dispatching resumed.")
    return 0


def cmd_coordinator(space: Workspace, args: argparse.Namespace) -> int:
    prompt = (
        "First rename this chat to `Coordinator`. You are the multiagent coordinator for "
        f"the primary repository at `{space.primary}`. Stay in the primary lane; do not adopt "
        "a sandbox lane. Read "
        "docs/development/multiagent-coordination.md, then report: issues waiting on my "
        "decision (owner:decision-needed), what is authorised (owner:ready), and what the "
        "controller is doing (scripts/dev/multiagent.py status). Help me draft requirements "
        "and answer blocked issues. Never add owner:ready yourself."
    )
    opened = run(
        ["code", "chat", "-m", "agent", "--reuse-window", prompt],
        timeout=60,
    )
    if opened.returncode != 0:
        log("Could not open VS Code chat. Start it yourself and paste this prompt:")
        log("")
        log(prompt)
        return 1
    log(
        "Coordinator chat opened in the last active VS Code window; "
        "its requested title is Coordinator."
    )
    return 0


def cmd_audit(space: Workspace, args: argparse.Namespace) -> int:
    """Run the read-only trip audit and propose issues for what is new."""
    repo = space.repo()
    audit = run(
        [space.python(), str(space.primary / "scripts" / "dev" / "trip_audit.py"), "--json"],
        cwd=space.primary,
        timeout=TEST_TIMEOUT_SECONDS,
    )
    # Exit 2 means the corpus was empty, which reads exactly like a clean run.
    if audit.returncode == 2:
        log("Audit read nothing: the corpus is empty. This is an infrastructure failure.")
        log("Build or restore a corpus before trusting a clean result.")
        return 2
    try:
        payload = json.loads(audit.stdout or "{}")
    except json.JSONDecodeError:
        log(f"Audit produced no usable JSON: {(audit.stderr or '').strip()[:300]}")
        return 2

    groups = [group for group in payload.get("groups", []) if group.get("new")]
    corpus = int(payload.get("corpus", 0))
    sources = [str(item) for item in payload.get("sources", [])]
    log(f"Corpus {corpus} trip(s); {len(groups)} new finding group(s).")
    if not groups:
        log("Nothing new to propose.")
        return 0

    kept, dropped = core.rank_findings(groups, args.cap)
    for group in kept:
        mark = core.fingerprint(str(group.get("rule", "?")), str(group.get("example", "")))
        title = f"[audit {group.get('rule', '?')}] {str(group.get('symptom', ''))[:70]}"
        body = core.audit_issue_body(group, corpus_size=corpus, sources=sources)
        if args.dry_run:
            log(f"  would propose  {mark}  {title}")
            continue
        existing = run([
            "gh", "issue", "list", "--repo", repo, "--state", "all", "--search", mark,
            "--json", "number,state", "--limit", "5",
        ])
        found = json.loads(existing.stdout or "[]") if existing.returncode == 0 else []
        if any(str(item.get("state", "")).lower() == "open" for item in found):
            log(f"  already open   {mark}")
            continue
        if found:
            number = found[0]["number"]
            run(["gh", "issue", "reopen", str(number), "--repo", repo])
            gh_comment(repo, number, "This finding recurs in the latest audit.")
            log(f"  reopened #{number}  {mark}")
            continue
        created = run([
            "gh", "issue", "create", "--repo", repo, "--title", title, "--body", body,
            "--label", "bug", "--label", core.PROPOSED, "--label", core.AUDIT_SOURCE,
        ])
        log(f"  proposed       {mark}  {created.stdout.strip() or created.stderr.strip()}")

    if dropped:
        log(f"{dropped} further group(s) exceeded the cap of {args.cap} and were not filed.")
        log("Raise --cap or triage the filed ones first.")
    log("Nothing is authorised. Add owner:ready to whichever should be built.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="what the controller, slots, and issues are doing")
    sub.add_parser("plan", help="dry run: what would be dispatched, and why not the rest")

    start = sub.add_parser("start", help="start the controller detached")
    start.add_argument("--interval", type=int, default=CYCLE_SECONDS)
    start.add_argument("--force", action="store_true", help="take over an expired lease")
    start.add_argument("--no-chat", action="store_true", help="do not open the coordinator chat")

    runner = sub.add_parser("run", help="the controller loop itself (foreground)")
    runner.add_argument("--interval", type=int, default=CYCLE_SECONDS)

    sub.add_parser("stop", help="stop the controller and its workers, keeping the evidence")
    pause = sub.add_parser("pause", help="stop dispatching; let running workers finish")
    pause.add_argument("--reason", default="")
    sub.add_parser("resume", help="resume dispatching")
    sub.add_parser("coordinator", help="open the owner-facing coordinator chat")

    audit = sub.add_parser("audit", help="run the read-only trip audit and propose issues")
    audit.add_argument("--dry-run", action="store_true")
    audit.add_argument("--cap", type=int, default=AUDIT_ISSUE_CAP)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    space = Workspace()
    handlers = {
        "status": cmd_status,
        "plan": cmd_plan,
        "start": cmd_start,
        "run": cmd_run,
        "stop": cmd_stop,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "coordinator": cmd_coordinator,
        "audit": cmd_audit,
    }
    return handlers[args.command](space, args)


if __name__ == "__main__":
    raise SystemExit(main())
