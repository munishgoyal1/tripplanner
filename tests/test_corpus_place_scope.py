from __future__ import annotations

import json

from tripplanner.harness.corpus import from_generated_finals, scope_places


def test_records_carry_only_the_places_their_plan_can_look_up(tmp_path) -> None:
    plan = {
        "destination": "Kandy",
        "day_wise_itinerary": [{"day": 1, "stops": [
            {"name": "Temple of the Tooth", "kind": "attraction"},
            {"name": "Train: Colombo to Kandy", "kind": "transport"},
        ]}],
    }
    places = {
        "temple of the tooth|kandy": {"name": "Sri Dalada Maligawa"},
        "kandy railway station|kandy": {"name": "Kandy Railway Station"},  # derived endpoint
        "colombo international airport|": {"name": "Bandaranaike International"},
        "india gate|delhi": {"name": "India Gate"},
    }

    scoped = scope_places(plan, places)

    assert sorted(scoped) == [
        "colombo international airport|",
        "kandy railway station|kandy",
        "temple of the tooth|kandy",
    ]

    (tmp_path / "trips").mkdir()
    (tmp_path / "trips" / "kandy.json").write_text(json.dumps(plan), encoding="utf-8")
    (record,) = from_generated_finals(tmp_path / "trips", places=places)
    assert record.places == scoped
