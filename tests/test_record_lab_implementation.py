from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "record-lab-implementation.ps1"


def write_store(path: Path) -> dict[str, object]:
    store = {
        "travel-documents": {
            "labId": "travel-documents",
            "labTitle": "Travel documents",
            "selection": "vault",
            "selectionLabel": "B · Account vault",
            "comment": "Keep originals out of storage.",
            "disposition": "ready",
            "handoffs": [{
                "version": 1,
                "selection": "vault",
                "selectionLabel": "B · Account vault",
                "comment": "Keep originals out of storage.",
                "disposition": "ready",
                "recordedAt": "2026-08-06T12:48:15.693Z",
            }],
            "implementations": [],
            "updatedAt": "2026-08-06T12:48:15.693Z",
        },
        "unrelated": {"labId": "unrelated", "selection": "a"},
    }
    path.write_text(json.dumps(store), encoding="utf-8")
    return store


def run_script(store_path: Path, evidence: str = "Commit abc123; 14 Labs tests passed.") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-LabId",
            "travel-documents",
            "-Evidence",
            evidence,
            "-StorePath",
            str(store_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def test_records_implementation_against_latest_handoff(tmp_path: Path) -> None:
    store_path = tmp_path / "selections.json"
    original = write_store(store_path)

    result = run_script(store_path)

    assert result.returncode == 0, result.stderr
    assert "implementation v1 -> handoff v1" in result.stdout
    stored = json.loads(store_path.read_text(encoding="utf-8-sig"))
    lab = stored["travel-documents"]
    assert lab["disposition"] == "implemented-review"
    assert lab["handoffs"] == original["travel-documents"]["handoffs"]
    assert lab["implementations"] == [{
        "version": 1,
        "handoffVersion": 1,
        "selection": "vault",
        "selectionLabel": "B · Account vault",
        "comment": "Keep originals out of storage.",
        "summary": "Commit abc123; 14 Labs tests passed.",
        "recordedAt": lab["updatedAt"],
    }]
    assert stored["unrelated"] == original["unrelated"]
    assert (tmp_path / "selections.previous.json").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_rejects_duplicate_implementation_without_changing_store(tmp_path: Path) -> None:
    store_path = tmp_path / "selections.json"
    write_store(store_path)
    first = run_script(store_path)
    before_duplicate = store_path.read_bytes()

    duplicate = run_script(store_path, "A second implementation")

    assert first.returncode == 0
    assert duplicate.returncode != 0
    assert "must be In progress with a ready handoff" in duplicate.stderr
    assert store_path.read_bytes() == before_duplicate


def test_rejects_a_parked_handoff_without_changing_store(tmp_path: Path) -> None:
    store_path = tmp_path / "selections.json"
    write_store(store_path)
    stored = json.loads(store_path.read_text(encoding="utf-8"))
    stored["travel-documents"]["disposition"] = "parked"
    store_path.write_text(json.dumps(stored), encoding="utf-8")
    before = store_path.read_bytes()

    result = run_script(store_path)

    assert result.returncode != 0
    assert "must be In progress with a ready handoff" in result.stderr
    assert store_path.read_bytes() == before


def test_preserves_singular_legacy_implementation(tmp_path: Path) -> None:
    store_path = tmp_path / "selections.json"
    write_store(store_path)
    stored = json.loads(store_path.read_text(encoding="utf-8"))
    stored["travel-documents"]["implementation"] = {
        "handoffVersion": 1,
        "selection": "vault",
        "selectionLabel": "B · Account vault",
        "comment": "Earlier implementation",
        "summary": "Commit old123.",
        "recordedAt": "2026-08-06T13:00:00.000Z",
    }
    store_path.write_text(json.dumps(stored), encoding="utf-8")
    result = run_script(store_path, "Commit new456.")

    assert result.returncode == 0, result.stderr
    updated = json.loads(store_path.read_text(encoding="utf-8-sig"))["travel-documents"]
    assert [entry["version"] for entry in updated["implementations"]] == [1, 2]
    assert updated["implementations"][0]["summary"] == "Commit old123."
    assert updated["implementations"][1]["summary"] == "Commit new456."