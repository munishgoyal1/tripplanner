from __future__ import annotations

import copy
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from tripplanner import api, public_demo, storage_cosmos


def test_bundle_has_ten_valid_standalone_artifacts() -> None:
    bundle = public_demo.load_bundle()

    assert len(bundle["artifacts"]) == 10
    assert len({id(item["trip"]) for item in bundle["artifacts"]}) == 10
    for artifact in bundle["artifacts"]:
        trip = artifact["trip"]
        day_numbers = [day["day"] for day in trip["days"]]
        markers = {hotel["marker"] for hotel in trip["hotels"]}
        entities = set(artifact["market"]["entities"])
        assert len(trip["days"]) >= 3
        assert len(trip["receipts"]) >= 6
        assert day_numbers == sorted(set(day_numbers))
        assert {receipt["day"] for receipt in trip["receipts"] if "day" in receipt} == set(
            day_numbers
        )
        assert all(len(day["stops"]) >= 2 for day in trip["days"])
        assert all(day["hotel"] in markers for day in trip["days"])
        assert all(
            stop.get("marker") in markers
            for day in trip["days"]
            for stop in day["stops"]
            if stop["kind"] == "hotel"
        )
        assert set(artifact["market"]["cities"]).issubset(entities)
        assert all(hotel["name"] in entities for hotel in trip["hotels"])
        assert all(
            stop["name"] in entities
            for day in trip["days"]
            for stop in day["stops"]
            if stop["kind"] in {"hotel", "attraction", "meal"}
        )
        assert trip["hotels"]
        assert trip["compares"]
        assert len(trip["lines"]) >= 2
        assert artifact["decisions"]
    assert public_demo.bundled_artifact("IN", "INR")["market"]["origin"] == "Mumbai"
    assert public_demo.bundled_artifact("JP", "JPY")["trip"]["title"] == "Tokyo to Kyoto"


def test_invalid_cosmos_artifact_falls_back_to_bundle(monkeypatch) -> None:
    public_demo.clear_active_cache()
    fallback = public_demo.bundled_artifact("IN", "INR")
    invalid = copy.deepcopy(fallback)
    invalid["trip"]["days"][0]["city"] = "Lisbon"
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(
        storage_cosmos,
        "read_doc",
        lambda _container, _partition, doc_id: (
            {"artifacts": {"IN:INR": "artifact:bad"}} if doc_id == "active-v1" else invalid
        ),
    )

    assert public_demo.active_artifact("IN", "INR") == fallback


def test_active_artifact_uses_in_process_cache(monkeypatch) -> None:
    public_demo.clear_active_cache()
    artifact = public_demo.bundled_artifact("IN", "INR")
    reads: list[str] = []
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)

    def read_doc(_container: str, _partition: str, doc_id: str):
        reads.append(doc_id)
        if doc_id == public_demo.MANIFEST_ID:
            return {"artifacts": {"IN:INR": "artifact:india"}}
        return artifact

    monkeypatch.setattr(storage_cosmos, "read_doc", read_doc)

    assert public_demo.active_artifact("IN", "INR") == artifact
    assert public_demo.active_artifact("IN", "INR") == artifact
    assert reads == [public_demo.MANIFEST_ID, "artifact:india"]


def test_public_demo_api_returns_cache_headers_and_etag(monkeypatch) -> None:
    public_demo.clear_active_cache()
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    client = TestClient(api.app)

    response = client.get("/public/demo-run", params={"region": "IN", "currency": "INR"})
    cached = client.get(
        "/public/demo-run",
        params={"region": "IN", "currency": "INR"},
        headers={"If-None-Match": response.headers["etag"]},
    )

    assert response.status_code == 200
    assert response.json()["region"] == "IN"
    assert response.headers["cache-control"].startswith("public, max-age=")
    assert cached.status_code == 304


def test_refresh_promotes_manifest_only_after_all_artifacts_are_written(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
    monkeypatch.setattr(storage_cosmos, "read_doc_versioned", lambda *_args: None)
    monkeypatch.setattr(
        storage_cosmos,
        "create_doc_if_absent",
        lambda _container, _partition, doc_id, _body: calls.append(("create", doc_id)),
    )

    manifest = public_demo.refresh(datetime(2026, 9, 1, tzinfo=UTC))

    assert len(manifest["artifacts"]) == 10
    assert calls[-1] == ("create", public_demo.MANIFEST_ID)
    assert all(doc_id.startswith("artifact:") for _, doc_id in calls[:-1])
