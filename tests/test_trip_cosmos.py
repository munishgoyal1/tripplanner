"""Ownership-focused tests split from the former tests/test_trip.py module."""

# ruff: noqa: E501, F403, F405, I001

from tests.support.trip import *  # noqa: F403

def test_restore_inspection_trip_writes_identity_copy_without_archiving(monkeypatch) -> None:
    source = {
        "trip_id": "spiti_valley_2027-06-01_2027-06-08",
        "user_id": "corpus-original",
        "destination": "Spiti Valley",
        "day_wise_itinerary": [{"day": 1, "stops": [{"name": "Narkanda"}]}],
    }
    monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: False)
    monkeypatch.setattr(
        trip_history.debug_store,
        "record_trip",
        lambda *_args, **_kwargs: pytest.fail("inspection must not alter the debug archive"),
    )
    token = user_context._user_id.set("corpus-spiti-food-friends-7d")
    try:
        restored = trip_planner.restore_inspection_trip(
            source,
            "corpus-spiti-food-friends-7d",
        )
    finally:
        user_context._user_id.reset(token)

    active = json.loads(
        (_TEST_DIR / "users/corpus-spiti-food-friends-7d/active_trip.json").read_text()
    )
    history = json.loads(
        (
            _TEST_DIR
            / "users/corpus-spiti-food-friends-7d/trips"
            / "spiti_valley_2027-06-01_2027-06-08.json"
        ).read_text()
    )
    assert restored["user_id"] == "corpus-spiti-food-friends-7d"
    assert active == history == restored
    assert source["user_id"] == "corpus-original"
    assert "updated_at" not in source

class TestCosmosDispatch:
    """When Cosmos is enabled, read/write go through storage_cosmos, not files."""

    def test_load_preferences_uses_cosmos(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc",
            lambda c, u, d: {"trip_style": "adventure", "budget_level": "premium"},
        )
        prefs = load_preferences()
        assert prefs["trip_style"] == "adventure"
        assert prefs["budget_level"] == "premium"
        # defaults still merged for unspecified keys
        assert prefs["family"]["adults"] == 1

    def test_load_preferences_cosmos_missing_returns_defaults(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(storage_cosmos, "read_doc", lambda c, u, d: None)
        prefs = load_preferences()
        assert prefs["trip_style"] == "balanced"

    def test_save_preferences_uses_cosmos(self, monkeypatch):
        captured: dict[str, object] = {}
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc_versioned",
            lambda c, u, d: None,
        )
        monkeypatch.setattr(
            storage_cosmos,
            "create_doc_if_absent",
            lambda c, u, d, body: captured.update(
                {"container": c, "user_id": u, "doc_id": d, "body": body}
            ),
        )
        save_preferences({"trip_style": "adventure"})
        assert captured["container"] == "users"
        assert captured["doc_id"] == "preferences"
        assert captured["user_id"] == "local"  # default user
        assert captured["body"]["trip_style"] == "adventure"

    def test_save_preferences_uses_current_user_id(self, monkeypatch):
        captured: dict[str, object] = {}
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc_versioned",
            lambda c, u, d: None,
        )
        monkeypatch.setattr(
            storage_cosmos,
            "create_doc_if_absent",
            lambda c, u, d, body: captured.update({"user_id": u}),
        )
        token = user_context._user_id.set("session-abc-123")
        try:
            save_preferences({"trip_style": "leisure"})
        finally:
            user_context._user_id.reset(token)
        assert captured["user_id"] == "session-abc-123"

    def test_update_preferences_replays_after_write_conflict(self, monkeypatch):
        state = {
            "body": {"trip_style": "balanced", "interests": ["museums"]},
            "version": '"v1"',
        }
        replace_calls = 0

        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc_versioned",
            lambda c, u, d: storage_cosmos.VersionedDocument(
                body=state["body"], version=state["version"]
            ),
        )

        def replace(_container, _user_id, _doc_id, body, version):
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 1:
                state["body"] = {
                    "trip_style": "leisure",
                    "interests": ["museums"],
                }
                state["version"] = '"v2"'
                raise storage_cosmos.WriteConflictError("concurrent update")
            assert version == '"v2"'
            state["body"] = body

        monkeypatch.setattr(storage_cosmos, "replace_doc_if_version", replace)

        result = update_preferences({"interests": ["hiking"]})

        assert replace_calls == 2
        assert result["trip_style"] == "leisure"
        assert result["interests"] == ["museums", "hiking"]

    def test_update_preferences_replays_after_create_conflict(self, monkeypatch):
        state = {"body": None, "version": None}
        create_calls = 0

        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)

        def read_versioned(_container, _user, _doc_id):
            if state["body"] is None:
                return None
            return storage_cosmos.VersionedDocument(
                body=state["body"], version=state["version"]
            )

        def create(_container, _user, _doc_id, _body):
            nonlocal create_calls
            create_calls += 1
            state["body"] = {"trip_style": "leisure", "interests": ["museums"]}
            state["version"] = '"v1"'
            raise storage_cosmos.WriteConflictError("concurrent create")

        def replace(_container, _user, _doc_id, body, version):
            assert version == '"v1"'
            state["body"] = body

        monkeypatch.setattr(storage_cosmos, "read_doc_versioned", read_versioned)
        monkeypatch.setattr(storage_cosmos, "create_doc_if_absent", create)
        monkeypatch.setattr(storage_cosmos, "replace_doc_if_version", replace)

        result = update_preferences({"interests": ["hiking"]})

        assert create_calls == 1
        assert result["trip_style"] == "leisure"
        assert result["interests"] == ["museums", "hiking"]

    def test_load_active_trip_uses_cosmos(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "read_doc",
            lambda c, u, d: {
                "destination": "Tokyo",
                "departure_date": "2026-09-01",
                "return_date": "2026-09-08",
                "status": "draft",
            },
        )
        result = get_trip_plan.invoke({})
        parsed = json.loads(result)
        assert parsed["destination"] == "Tokyo"
        assert parsed["status"] == "draft"

    def test_create_trip_plan_writes_to_cosmos(self, monkeypatch):
        captured: list[dict[str, object]] = []
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        # read_doc is called for preferences (load_preferences) and active_trip
        # — return None so defaults are used and no existing plan is found.
        monkeypatch.setattr(storage_cosmos, "read_doc", lambda c, u, d: None)
        monkeypatch.setattr(storage_cosmos, "read_doc_versioned", lambda c, u, d: None)
        monkeypatch.setattr(
            storage_cosmos,
            "upsert_doc",
            lambda c, u, d, body: captured.append(
                {"container": c, "doc_id": d, "body": body}
            ),
        )
        monkeypatch.setattr(
            storage_cosmos,
            "create_doc_if_absent",
            lambda c, u, d, body: captured.append(
                {"container": c, "doc_id": d, "body": body}
            ),
        )
        result = create_trip_plan.invoke({
            "destination": "Bali",
            "departure_date": "2026-10-01",
            "return_date": "2026-10-07",
        })
        assert "Bali" in result
        # The full plan is canonical in trips; active_trip is only a pointer.
        active_writes = [
            c for c in captured
            if c["container"] == "users" and c["doc_id"] == "active_trip"
        ]
        assert len(active_writes) == 1
        assert active_writes[0]["body"] == {
            "trip_id": "bali_2026-10-01_2026-10-07",
            "revision": 1,
        }
        trip_writes = [c for c in captured if c["container"] == "trips"]
        assert len(trip_writes) == 1
        assert trip_writes[0]["body"]["destination"] == "Bali"

    def test_execute_bookings_deletes_active_trip_from_cosmos(self, monkeypatch):
        # State machine: cosmos read returns a finalized plan, then upserts and
        # deletes get captured. Mock all read_doc calls (prefs + active_trip).
        active_plan = {
            "destination": "Bali",
            "departure_date": "2026-10-01",
            "return_date": "2026-10-07",
            "travelers": "2 adults",
            "selected_flights": [{"airline": "AI", "price": 5000}],
            "selected_hotels": [{"name": "Hotel", "price": 8000}],
            "selected_activities": [],
            "day_wise_itinerary": [],
            "cost_breakdown": {},
            "total_cost": 13000,
            "notes": "",
            "status": "finalized",
        }
        delete_calls: list[tuple[str, str, str]] = []
        upsert_calls: list[tuple[str, str, str]] = []

        def _read(container: str, user: str, doc_id: str):
            if doc_id == "active_trip":
                return dict(active_plan)
            return None  # preferences fall back to defaults

        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(storage_cosmos, "read_doc", _read)
        monkeypatch.setattr(storage_cosmos, "read_doc_versioned", lambda c, u, d: None)
        monkeypatch.setattr(
            storage_cosmos,
            "upsert_doc",
            lambda c, u, d, body: upsert_calls.append((c, u, d)),
        )
        monkeypatch.setattr(
            storage_cosmos,
            "create_doc_if_absent",
            lambda c, u, d, body: upsert_calls.append((c, u, d)),
        )
        monkeypatch.setattr(
            storage_cosmos,
            "delete_doc",
            lambda c, u, d: delete_calls.append((c, u, d)),
        )

        result = execute_bookings.invoke({})
        assert "All bookings executed" in result
        assert ("users", "local", "active_trip") in delete_calls
        # The archived trip should be written to the trips container.
        assert any(c == "trips" for c, _, _ in upsert_calls)

    def test_list_past_trips_queries_cosmos(self, monkeypatch):
        monkeypatch.setattr(storage_cosmos, "is_enabled", lambda: True)
        monkeypatch.setattr(
            storage_cosmos,
            "query_docs",
            lambda c, u: [
                {
                    "destination": "Goa",
                    "departure_date": "2025-06-01",
                    "return_date": "2025-06-05",
                    "total_cost": 25000,
                    "status": "booked",
                },
                {
                    "destination": "Kerala",
                    "departure_date": "2025-12-10",
                    "return_date": "2025-12-15",
                    "total_cost": 30000,
                    "status": "booked",
                },
            ],
        )
        result = list_past_trips.invoke({})
        assert "Goa" in result
        assert "Kerala" in result

class TestUserContext:
    """ContextVar default + scoped override behavior."""

    def test_default_user_id(self):
        assert user_context.get_user_id() == "local"
        assert user_context.is_default_user() is True

    def test_set_and_reset_user_id(self):
        token = user_context._user_id.set("alice")
        try:
            assert user_context.get_user_id() == "alice"
            assert user_context.is_default_user() is False
        finally:
            user_context._user_id.reset(token)
        assert user_context.get_user_id() == "local"
