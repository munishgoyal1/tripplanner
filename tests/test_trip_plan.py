"""Ownership-focused tests split from the former tests/test_trip.py module."""

# ruff: noqa: E501, F403, F405, I001

from tests.support.trip import *  # noqa: F403

class TestPartialItineraryMerge:
    """A single-stop edit must not delete the days the model did not resend."""

    def _days(self, *numbers: int) -> list[dict]:
        return [{"day": n, "stops": [{"name": f"Stop {n}", "kind": "attraction"}]} for n in numbers]

    def test_subset_of_planned_days_is_merged_in_place(self):
        existing = self._days(1, 2, 3)
        incoming = [{"day": 2, "stops": [{"name": "Budget Inn Indore", "kind": "hotel"}]}]

        merged, partial = _merge_itinerary_days(existing, incoming)

        assert partial is True
        assert [day["day"] for day in merged] == [1, 2, 3]
        assert merged[1] == incoming[0]
        assert merged[0] == existing[0]

    def test_full_resubmit_replaces_the_itinerary(self):
        existing = self._days(1, 2, 3)
        incoming = self._days(1, 2)
        incoming.append({"day": 3, "stops": []})

        merged, partial = _merge_itinerary_days(existing, incoming)

        assert partial is False
        assert merged == incoming

    def test_shorter_itinerary_with_a_new_day_replaces(self):
        merged, partial = _merge_itinerary_days(self._days(1, 2, 3), self._days(4))

        assert partial is False
        assert [day["day"] for day in merged] == [4]

    def test_unnumbered_days_replace(self):
        incoming = [{"stops": []}]

        merged, partial = _merge_itinerary_days(self._days(1, 2), incoming)

        assert partial is False
        assert merged == incoming

    @pytest.mark.parametrize("invalid", [[], ["Day 1"], [{"day": 1}]])
    def test_unstructured_itinerary_update_does_not_erase_saved_days(self, invalid):
        existing = self._days(1, 2, 3)
        create_trip_plan.invoke({
            "destination": "Indore",
            "departure_date": "2026-08-10",
            "return_date": "2026-08-12",
            "origin": "Bangalore",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": existing,
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": invalid,
        })})

        assert result.startswith("Error: day_wise_itinerary must contain")
        assert json.loads(get_trip_plan.invoke({}))["day_wise_itinerary"] == existing

    def test_hotel_swap_keeps_the_other_planned_days(self):
        create_trip_plan.invoke({
            "destination": "Indore",
            "departure_date": "2026-08-10",
            "return_date": "2026-08-12",
            "origin": "Bangalore",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": self._days(1, 2, 3),
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": 2,
                    "stops": [{"name": "Lemon Tree Hotel Indore", "kind": "hotel"}],
                },
            ],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert [day["day"] for day in plan["day_wise_itinerary"]] == [1, 2, 3]
        assert plan["day_wise_itinerary"][1]["stops"][0]["name"] == "Lemon Tree Hotel Indore"
        assert "Partial itinerary update merged" in result

class TestTripPlanState:
    @staticmethod
    def _save_booking_ready_trip(**updates):
        plan = {
            "status": "draft",
            "destination": "Goa",
            "origin": "",
            "travel_scope": "destination_only",
            "departure_date": "2026-07-06",
            "return_date": "2026-07-06",
            "travelers": "1 adult",
            "selected_flights": [],
            "selected_hotels": [{"name": "Taj Goa", "city": "Goa", "price": 15000}],
            "selected_activities": [],
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Taj Goa", "kind": "hotel", "time": "09:00"},
                        {
                            "name": "Riverside Walk",
                            "kind": "attraction",
                            "time": "11:00",
                            "duration_min": 60,
                        },
                    ],
                }
            ],
            "cost_breakdown": {},
            "total_cost": 15000,
            "currency": "INR",
        }
        plan.update(updates)
        trip_planner._save_active_trip(plan)

    def test_save_normalizes_duplicate_return_stay_and_departure_checkout(self):
        plan = {
            "destination": "Ayodhya",
            "departure_date": "2026-09-10",
            "return_date": "2026-09-16",
            "day_wise_itinerary": [
                {
                    "day": 6,
                    "stops": [
                        {"name": "Drive: Chitrakoot to Ayodhya", "kind": "transport"},
                        {"name": "Ayodhya Hotel", "kind": "hotel", "time": "22:30"},
                        {"name": "Ayodhya Hotel", "kind": "hotel", "time": "23:59"},
                    ],
                },
                {
                    "day": 7,
                    "title": "Departure from Ayodhya",
                    "summary": "Check out from hotel and depart from Ayodhya.",
                    "stops": [{"name": "Ayodhya Hotel", "kind": "hotel", "note": "Check-out"}],
                },
            ],
        }

        trip_planner._save_active_trip(plan)

        saved = trip_planner.load_active_trip_dict()
        assert saved is not None
        assert saved["day_wise_itinerary"][0]["stops"] == [
            {"name": "Drive: Chitrakoot to Ayodhya", "kind": "transport"},
            {
                "name": "Ayodhya Hotel",
                "kind": "hotel",
                "time": "22:30",
                "note": "Return to hotel",
            },
        ]
        departure = saved["day_wise_itinerary"][1]["stops"][0]
        assert departure["time"] == "11:00"
        assert "confirm with your hotel" in departure["note"]

    def test_planning_completion_requires_round_trip_intercity_transport(self):
        base = {
            "origin": "Bangalore",
            "destination": "Mysore",
            "selected_hotels": [{"name": "Radisson Blu Plaza Mysore"}],
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Mysore Palace", "kind": "attraction"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Taxi to Mysore Palace", "kind": "transport"},
                    ],
                },
            ],
        }

        gaps = planning_completion_gaps(base)

        assert any("Bangalore to Mysore" in gap for gap in gaps)
        assert any("Mysore back to Bangalore" in gap for gap in gaps)

        unrelated_transport = {
            **base,
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Train: Chennai to Mysore", "kind": "transport"},
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Bus: Mysore to Chennai", "kind": "transport"},
                    ],
                },
            ],
        }
        assert len([
            gap for gap in planning_completion_gaps(unrelated_transport)
            if "journey from" in gap
        ]) == 2

        no_hotel_boundaries = {
            **base,
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Train: Bangalore to Mysore", "kind": "transport"}],
            }],
        }
        assert len([
            gap for gap in planning_completion_gaps(no_hotel_boundaries)
            if "journey from" in gap
        ]) == 2

        create_trip_plan.invoke({
            "destination": "Mysore",
            "departure_date": "2026-08-10",
            "return_date": "2026-08-11",
            "origin": "Bangalore",
        })
        save_result = update_trip_plan.invoke({"updates_json": json.dumps(base)})
        assert "The itinerary was saved but is not yet consistent:" in save_result
        assert "Bangalore to Mysore" in save_result
        assert "Mysore back to Bangalore" in save_result
        # An incomplete journey must never cost the traveller the whole itinerary.
        assert json.loads(get_trip_plan.invoke({}))["day_wise_itinerary"]

        complete = {
            **base,
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Train: Bengaluru to Mysuru", "kind": "transport"},
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Mysore Palace", "kind": "attraction"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Radisson Blu Plaza Mysore", "kind": "hotel"},
                        {"name": "Train: Mysuru to Bengaluru", "kind": "transport"},
                    ],
                },
            ],
        }
        complete_gaps = planning_completion_gaps(complete)

        assert not any("journey from" in gap for gap in complete_gaps)

    def test_create_trip_plan(self):
        result = create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
            "origin": "Delhi",
        })
        assert "Goa" in result
        assert "DRAFT" in result

    def test_create_trip_plan_defaults_origin_from_saved_home_area(self):
        update_preferences({
            "profile": {"home_city": "Bangalore", "home_area": "Whitefield"},
        })

        create_trip_plan.invoke({
            "destination": "Coorg",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })

        parsed = json.loads(get_trip_plan.invoke({}))
        assert parsed["origin"] == "Whitefield, Bangalore"
        assert parsed["travel_scope"] == "round_trip"

    def test_create_trip_plan_persists_self_arranged_arrival_without_origin(self):
        update_preferences({"profile": {"home_city": "Bangalore"}})

        create_trip_plan.invoke({
            "destination": "Pondicherry",
            "departure_date": "2026-11-07",
            "return_date": "2026-11-09",
            "travel_scope": "destination_only",
        })

        parsed = json.loads(get_trip_plan.invoke({}))
        assert parsed["origin"] == ""
        assert parsed["travel_scope"] == "destination_only"

    def test_resume_keeps_existing_explicit_origin(self):
        create_trip_plan.invoke({
            "destination": "Coorg",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
            "origin": "Mysore",
        })
        update_preferences({"profile": {"home_city": "Bangalore"}})

        create_trip_plan.invoke({
            "destination": "Coorg",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })

        parsed = json.loads(get_trip_plan.invoke({}))
        assert parsed["origin"] == "Mysore"

    def test_get_trip_plan(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        result = get_trip_plan.invoke({})
        parsed = json.loads(result)
        assert parsed["destination"] == "Goa"
        assert parsed["status"] == "draft"

    def test_get_trip_plan_no_plan(self):
        result = get_trip_plan.invoke({})
        assert "No active trip plan" in result

    def test_update_trip_plan(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update = json.dumps({
            "selected_flights": [{"airline": "IndiGo", "price": 8500}],
            "weather": {
                "source": "forecast",
                "days": [{"date": "2026-07-01", "summary": "Rain", "high_c": 29}],
            },
            "total_cost": 8500,
        })
        result = update_trip_plan.invoke({"updates_json": update})
        assert "updated" in result

        plan = json.loads(get_trip_plan.invoke({}))
        assert len(plan["selected_flights"]) == 1
        assert plan["weather"]["source"] == "forecast"
        assert plan["total_cost"] == 8500

    def test_update_trip_plan_moves_known_closed_day_before_persistence(
        self, monkeypatch
    ):
        weekdays = (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )

        def structured_hours(name, _destination):
            if name != "Closed Museum":
                return {}
            return {
                "name": name,
                "weekday_descriptions": [
                    f"{day}: {'Closed' if day == 'Tuesday' else '9:00 AM - 6:00 PM'}"
                    for day in weekdays
                ],
            }

        monkeypatch.setattr(
            "tripplanner.tools.trip_guard._summary_for_place",
            structured_hours,
        )
        create_trip_plan.invoke(
            {
                "destination": "Paris",
                "departure_date": "2026-09-07",
                "return_date": "2026-09-08",
                "travel_scope": "destination_only",
            }
        )

        result = update_trip_plan.invoke(
            {
                "updates_json": json.dumps(
                    {
                        "day_wise_itinerary": [
                            {
                                "day": 1,
                                "stops": [{"name": "Hotel Lutetia", "kind": "hotel"}],
                            },
                            {
                                "day": 2,
                                "stops": [
                                    {
                                        "name": "Closed Museum",
                                        "kind": "attraction",
                                        "time": "10:00",
                                        "duration_min": 90,
                                    }
                                ],
                            },
                        ]
                    }
                )
            }
        )

        saved = json.loads(get_trip_plan.invoke({}))
        assert [
            stop["name"]
            for stop in saved["day_wise_itinerary"][0]["stops"]
            if stop["kind"] == "attraction"
        ] == ["Closed Museum"]
        assert saved["day_wise_itinerary"][1]["stops"] == []
        assert "Adjusted known closed-day visits before saving" in result

    def test_update_trip_plan_moves_wat_kaew_korawaram_off_sunday(self, monkeypatch):
        weekdays = (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )

        def wat_hours(name, _destination):
            if name != "Wat Kaew Korawaram":
                return {}
            return {
                "name": name,
                "weekday_descriptions": [
                    f"{day}: {'Closed' if day == 'Sunday' else '8:00 AM - 6:00 PM'}"
                    for day in weekdays
                ],
            }

        monkeypatch.setattr(
            "tripplanner.tools.trip_guard._summary_for_place",
            wat_hours,
        )
        create_trip_plan.invoke(
            {
                "destination": "Thailand",
                "departure_date": "2027-01-09",
                "return_date": "2027-01-12",
                "origin": "Chennai",
            }
        )
        submitted = {
            "destination": "Thailand",
            "departure_date": "2027-01-09",
            "day_wise_itinerary": [
                {"day": 1, "date": "2027-01-09", "stops": []},
                {
                    "day": 2,
                    "date": "2027-01-10",
                    "stops": [
                        {
                            "name": "Wat Kaew Korawaram",
                            "kind": "attraction",
                            "time": "15:00",
                            "duration_min": 90,
                        }
                    ],
                },
                {"day": 3, "date": "2027-01-11", "stops": []},
            ],
        }

        from tripplanner.tools import trip_guard

        assert [item.code for item in trip_guard.validate_plan(submitted) if item.code == "I11"] == [
            "I11"
        ]

        result = update_trip_plan.invoke(
            {"updates_json": json.dumps({"day_wise_itinerary": submitted["day_wise_itinerary"]})}
        )

        saved = json.loads(get_trip_plan.invoke({}))
        assert not [item for item in trip_guard.validate_plan(saved) if item.code == "I11"]
        wat_days = [
            day["day"]
            for day in saved["day_wise_itinerary"]
            if any(stop.get("name") == "Wat Kaew Korawaram" for stop in day["stops"])
        ]
        assert wat_days in ([1], [3])
        assert "Adjusted known closed-day visits before saving" in result

    def test_update_trip_plan_repairs_visit_across_split_opening_hours(self, monkeypatch):
        weekdays = (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        )
        monkeypatch.setattr(
            "tripplanner.tools.trip_guard._summary_for_place",
            lambda name, _destination: {
                "name": name,
                "weekday_descriptions": [
                    f"{day}: 6:00 AM - 12:00 PM, 6:00 PM - 9:00 PM"
                    for day in weekdays
                ],
            }
            if name == "Sri Mariamman Temple"
            else {},
        )
        create_trip_plan.invoke(
            {
                "destination": "Singapore",
                "departure_date": "2027-06-04",
                "return_date": "2027-06-09",
                "travel_scope": "destination_only",
            }
        )
        itinerary = [{"day": day, "stops": []} for day in range(1, 7)]
        itinerary[3]["stops"] = [
            {
                "name": "Sri Mariamman Temple",
                "kind": "attraction",
                "time": "11:30",
                "duration_min": 60,
            }
        ]
        submitted = {
            "destination": "Singapore",
            "departure_date": "2027-06-04",
            "day_wise_itinerary": itinerary,
        }

        from tripplanner.tools import trip_guard

        violations = [
            item.message for item in trip_guard.validate_plan(submitted) if item.code == "I3"
        ]
        assert violations == [
            "Sri Mariamman Temple is open 06:00-12:00, 18:00-21:00; "
            "the Day 4 visit runs 11:30–12:30."
        ]

        result = update_trip_plan.invoke(
            {"updates_json": json.dumps({"day_wise_itinerary": itinerary})}
        )

        saved = json.loads(get_trip_plan.invoke({}))
        assert "Adjusted visits to fit known opening hours before saving" in result
        assert not [item for item in trip_guard.validate_plan(saved) if item.code == "I3"]

    def test_update_trip_plan_does_not_infer_closed_day_from_unknown_hours(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            "tripplanner.tools.trip_guard._summary_for_place",
            lambda *_: {},
        )
        create_trip_plan.invoke(
            {
                "destination": "Paris",
                "departure_date": "2026-09-07",
                "return_date": "2026-09-08",
                "travel_scope": "destination_only",
            }
        )
        itinerary = [
            {
                "day": 1,
                "stops": [{"name": "Hotel Lutetia", "kind": "hotel"}],
            },
            {
                "day": 2,
                "stops": [
                    {
                        "name": "Unknown Museum",
                        "kind": "attraction",
                        "time": "10:00",
                        "duration_min": 90,
                    }
                ],
            },
        ]

        result = update_trip_plan.invoke(
            {"updates_json": json.dumps({"day_wise_itinerary": itinerary})}
        )

        saved = json.loads(get_trip_plan.invoke({}))
        assert saved["day_wise_itinerary"] == itinerary
        assert "Adjusted known closed-day visits before saving" not in result

    def test_update_trip_plan_owns_numeric_budget_as_structured_user_target(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })

        update_trip_plan.invoke(
            {"updates_json": json.dumps({"budget": 100000, "currency": "INR"})}
        )

        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["budget"]["amount"] == 100000
        assert plan["budget"]["currency"] == "INR"
        assert plan["budget"]["owner"] == "user"
        assert plan["budget"]["updated_at"]

    def test_update_trip_plan_rejects_placeholder_hotel_selection(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "Hotel (TBD)", "price": 15000}],
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["selected_hotels"] == []
        assert "Hotel planning incomplete" in result
        assert "search_hotels" in result

    def test_update_trip_plan_rejects_generic_city_hotel_selections(self):
        create_trip_plan.invoke({
            "destination": "Kochi, Kerala",
            "departure_date": "2026-12-12",
            "return_date": "2026-12-18",
        })
        before = json.loads(get_trip_plan.invoke({}))
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [
                {"name": "Hotel in Kochi", "price": 15000},
                {"name": "Kochi Hotel", "price": 14000},
            ],
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Hotel in Kochi", "kind": "hotel"}],
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        # The itinerary is saved rather than discarded, and the generic stay is warned about.
        assert plan != before
        assert "no bookable property" in result

    def test_update_trip_plan_accepts_concrete_hotel_selection(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "DoubleTree by Hilton Goa - Panaji"}],
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{
                    "name": "DoubleTree by Hilton Goa - Panaji",
                    "kind": "hotel",
                }],
            }],
        })})

        assert "Hotel planning incomplete" not in result

    def test_update_trip_plan_replaces_unnamed_anchors_with_concrete_hotel(self):
        create_trip_plan.invoke({
            "destination": "Paris",
            "departure_date": "2027-04-05",
            "return_date": "2027-04-12",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Hotel Le Six",
                "city": "Paris",
                "address": "14 Rue Stanislas, Paris",
            }],
            "day_wise_itinerary": [
                {
                    "day": day,
                    "stops": [{"name": "Paris Hotel", "kind": "hotel"}],
                }
                for day in range(1, 8)
            ],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert {stop["name"] for stop in hotel_stops} == {"Hotel Le Six"}
        assert all(stop["address"] == "14 Rue Stanislas, Paris" for stop in hotel_stops)
        assert "no bookable property" not in result

    def test_one_named_hotel_cannot_mask_unnamed_stays_in_other_cities(self):
        create_trip_plan.invoke({
            "destination": "Rajasthan",
            "departure_date": "2027-02-02",
            "return_date": "2027-02-10",
        })
        before = json.loads(get_trip_plan.invoke({}))
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Twinstar Standard",
                "city": "Jaipur",
                "address": "Jaipur City Center",
            }],
            "day_wise_itinerary": [
                {
                    "day": day,
                    "city": city,
                    "stops": [{
                        "name": f"Hotel in {city}",
                        "kind": "hotel",
                    }],
                }
                for day, city in enumerate(
                    [
                        "Jaipur",
                        "Jaipur",
                        "Jodhpur",
                        "Jodhpur",
                        "Jodhpur",
                        "Udaipur",
                        "Udaipur",
                        "Udaipur",
                    ],
                    start=1,
                )
            ],
        })})

        # The itinerary is saved rather than discarded, and the unnamed stays are warned about.
        assert json.loads(get_trip_plan.invoke({})) != before
        assert "Day(s) 3, 4, 5, 6, 7, 8 name no bookable property" in result

    def test_selected_gangtok_stay_cannot_mask_lachen_placeholders(self):
        create_trip_plan.invoke({
            "destination": "Gangtok & North Sikkim",
            "departure_date": "2027-10-04",
            "return_date": "2027-10-07",
        })
        before = json.loads(get_trip_plan.invoke({}))

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "The Elgin Nor-Khill",
                "city": "Gangtok",
                "address": "Paljor Stadium Road, Gangtok, Sikkim, India",
            }],
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "city": "Gangtok",
                    "stops": [{"name": "The Elgin Nor-Khill", "kind": "hotel"}],
                },
                {
                    "day": 2,
                    "city": "Lachen",
                    "stops": [{"name": "Premium Hotel Lachen (TBD)", "kind": "hotel"}],
                },
                {
                    "day": 3,
                    "city": "Lachen",
                    "stops": [{"name": "Premium Hotel Lachen (TBD)", "kind": "hotel"}],
                },
            ],
        })})

        # The itinerary is saved rather than discarded, and the placeholders are warned about.
        assert json.loads(get_trip_plan.invoke({})) != before
        assert "Hotel placeholders remain on Day(s) 2, 3" in result

    def test_update_trip_plan_replaces_placeholder_anchors_with_concrete_hotel(self):
        create_trip_plan.invoke({
            "destination": "Mauritius",
            "departure_date": "2026-08-28",
            "return_date": "2026-09-03",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Hotel (TBD)", "kind": "hotel", "time": "09:00"},
                    {"name": "Blue Bay Marine Park", "kind": "attraction", "time": "10:00"},
                    {"name": "Hotel (TBD)", "kind": "hotel", "time": "18:00"},
                ],
            }],
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Preskil Island Resort",
                "destination": "Mauritius",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert "Hotel planning incomplete" not in result
        assert {stop["name"] for stop in hotel_stops} == {"Preskil Island Resort"}
        assert [stop["time"] for stop in hotel_stops] == ["09:00", "18:00"]

    def test_update_trip_plan_replaces_multi_city_placeholder_anchors(self):
        create_trip_plan.invoke({
            "destination": "Istanbul and Cappadocia",
            "departure_date": "2027-05-10",
            "return_date": "2027-05-18",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [
                {
                    "name": "Mest Hotel Istanbul Sirkeci",
                    "city": "Istanbul",
                    "address": "Cicek Pazari Sokak 22, Istanbul",
                },
                {
                    "name": "Museum Hotel",
                    "city": "Cappadocia",
                    "address": "Tekeli Mahallesi, Uchisar, Cappadocia",
                },
            ],
            "day_wise_itinerary": [
                {
                    "day": day,
                    "city": city,
                    "destination": "Istanbul and Cappadocia",
                    "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
                }
                for day, city in enumerate(
                    [
                        "Istanbul",
                        "Istanbul",
                        "Istanbul",
                        "Istanbul",
                        "Cappadocia",
                        "Cappadocia",
                        "Cappadocia",
                        "Cappadocia",
                    ],
                    start=1,
                )
            ],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_names_by_day = [
            day["stops"][0]["name"] for day in plan["day_wise_itinerary"]
        ]
        assert hotel_names_by_day == [
            *(["Mest Hotel Istanbul Sirkeci"] * 4),
            *(["Museum Hotel"] * 4),
        ]
        assert "Hotel placeholders remain" not in result

    def test_itinerary_update_cannot_restore_generic_or_placeholder_hotel(self):
        create_trip_plan.invoke({
            "destination": "Gujarat",
            "departure_date": "2026-12-07",
            "return_date": "2026-12-12",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Rann Utsav Tent City",
                "city": "Kutch",
                "address": "Dhordo, Kutch, Gujarat",
            }],
            "day_wise_itinerary": [{
                "day": 3,
                "city": "Kutch",
                "stops": [{"name": "Rann Utsav Tent City", "kind": "hotel"}],
            }],
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": day,
                    "stops": [{"name": "Hotel (TBD)", "kind": "hotel"}],
                }
                for day in range(3, 6)
            ],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert {stop["name"] for stop in hotel_stops} == {"Rann Utsav Tent City"}
        assert "Hotel placeholders remain" not in result

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": day,
                    "city": "Kutch",
                    "stops": [{"name": "Hotel (Kutch)", "kind": "hotel"}],
                }
                for day in range(3, 6)
            ],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert {stop["name"] for stop in hotel_stops} == {"Rann Utsav Tent City"}
        assert "no bookable property" not in result

    def test_update_trip_plan_rejects_hotel_outside_destination_atomically(self):
        create_trip_plan.invoke({
            "destination": "Manali, India",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Mountain Luxury Resort",
                "destination": "Queenstown, New Zealand",
                "address": "Kawarau Village, Queenstown, New Zealand",
            }],
            "total_cost": 125000,
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert result.startswith("Error: hotel location must match")
        assert "outside the trip destination 'Manali, India'" in result
        assert plan["selected_hotels"] == []
        assert plan["total_cost"] == 0

    def test_update_trip_plan_accepts_hotel_with_matching_destination_evidence(self):
        create_trip_plan.invoke({
            "destination": "Manali, India",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "The Himalayan",
                "destination": "Manali",
                "address": "Hadimba Road, Manali, Himachal Pradesh, India",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert not result.startswith("Error:")
        assert plan["selected_hotels"][0]["name"] == "The Himalayan"

    def test_update_trip_plan_accepts_hotel_in_evidenced_itinerary_city(self):
        create_trip_plan.invoke({
            "destination": "Madhya Pradesh",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "Old Indore Hotel", "city": "Indore"}],
            "day_wise_itinerary": [{
                "day": 1,
                "city": "Indore",
                "stops": [{"name": "Old Indore Hotel", "kind": "hotel"}],
            }],
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "WOW Hotel Indore",
                "city": "Indore",
                "address": "AB Road, Indore, Madhya Pradesh, India",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert not result.startswith("Error:")
        assert plan["selected_hotels"][0]["name"] == "WOW Hotel Indore"
        assert plan["day_wise_itinerary"][0]["stops"][0]["name"] == "WOW Hotel Indore"

    def test_update_trip_plan_replaces_hotel_in_itinerary_anchors(self, monkeypatch):
        from tripplanner.web import trip_view

        def place_details(name, _destination):
            coords = {
                "The Himalayan": (32.25, 77.18),
                "Hadimba Temple": (32.24, 77.19),
                "Solang Valley": (32.32, 77.16),
            }
            lat, lng = coords.get(name, (32.24, 77.18))
            return {"name": name, "lat": lat, "lng": lng}

        monkeypatch.setattr(
            trip_view.places_cache, "top_places", lambda *_args, **_kwargs: []
        )
        monkeypatch.setattr(
            trip_view.places_cache, "prefetch", lambda *_args, **_kwargs: None
        )
        monkeypatch.setattr(trip_view.places_cache, "get_details", place_details)
        monkeypatch.setattr(trip_view.places_cache, "get_photos", lambda *_args, **_kwargs: [])
        monkeypatch.setattr(trip_view, "_airport_pin", lambda _destination: None)
        create_trip_plan.invoke({
            "destination": "Manali, India",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Wrong Mountain Resort",
                "destination": "Manali",
            }],
            "day_wise_itinerary": [
                {"day": 1, "stops": [
                    {"name": "Wrong Mountain Resort", "kind": "hotel", "time": "09:00"},
                    {"name": "Hadimba Temple", "kind": "attraction", "time": "10:00"},
                    {"name": "Wrong Mountain Resort", "kind": "hotel", "time": "18:00"},
                ]},
                {"day": 2, "stops": [
                    {"name": "Wrong Mountain Resort", "kind": "hotel", "time": "09:00"},
                    {"name": "Solang Valley", "kind": "attraction", "time": "10:00"},
                    {"name": "Wrong Mountain Resort", "kind": "hotel", "time": "18:00"},
                ]},
            ],
        })})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "The Himalayan",
                "destination": "Manali",
                "address": "Hadimba Road, Manali, Himachal Pradesh, India",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        hotel_stops = [
            stop
            for day in plan["day_wise_itinerary"]
            for stop in day["stops"]
            if stop.get("kind") == "hotel"
        ]
        assert not result.startswith("Error:")
        assert {stop["name"] for stop in hotel_stops} == {"The Himalayan"}
        assert [stop["time"] for stop in hotel_stops] == [
            "09:00", "18:00", "09:00", "18:00",
        ]
        assert all(stop["address"].startswith("Hadimba Road") for stop in hotel_stops)
        map_names = {pin["name"] for pin in trip_view.build_map_view(plan)["pins"]}
        assert "The Himalayan" in map_names
        assert "Wrong Mountain Resort" not in map_names

    def test_update_trip_plan_rejects_hotel_without_destination_evidence(self):
        create_trip_plan.invoke({
            "destination": "Manali, India",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{
                "name": "Mystery Luxury Resort",
                "search_destination": "Manali, India",
            }],
        })})

        plan = json.loads(get_trip_plan.invoke({}))
        assert "has no location evidence matching" in result
        assert plan["selected_hotels"] == []

    def test_update_trip_plan_warns_about_restaurant_placeholders(self):
        create_trip_plan.invoke({
            "destination": "Kolkata",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Victoria Memorial", "kind": "attraction"},
                    {"name": "Indian Museum", "kind": "attraction"},
                    {"name": "Dinner TBD", "kind": "meal"},
                ],
            }],
        })})

        assert "Restaurant planning incomplete" in result
        assert "nearby_restaurants" in result

    def test_update_trip_plan_accepts_named_restaurants(self):
        create_trip_plan.invoke({
            "destination": "Kolkata",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Victoria Memorial", "kind": "attraction"},
                    {"name": "Indian Museum", "kind": "attraction"},
                    {"name": "Peter Cat", "kind": "restaurant"},
                ],
            }],
        })})

        assert "Restaurant planning incomplete" not in result

    def test_update_trip_plan_warns_when_full_day_has_no_restaurant(self):
        create_trip_plan.invoke({
            "destination": "Kolkata",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Victoria Memorial", "kind": "attraction"},
                    {"name": "Indian Museum", "kind": "attraction"},
                ],
            }],
        })})

        assert "Day 1 has multiple activities but no named restaurant stop" in result

    def test_update_trip_plan_warns_about_hotel_only_days(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "Holiday Inn Resort Goa"}],
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Holiday Inn Resort Goa", "kind": "hotel"},
                    {"name": "Holiday Inn Resort Goa", "kind": "hotel"},
                ],
            }],
        })})

        assert "Itinerary planning incomplete" in result
        assert "Day 1 has no planned places beyond the hotel" in result

    def test_update_trip_plan_accepts_transport_only_travel_day(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [{"name": "Overnight train to Goa", "kind": "transport"}],
            }],
        })})

        assert "no planned places beyond the hotel" not in result

    def test_update_trip_plan_rejects_duplicate_or_backwards_visit_times_atomically(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        original = [{
            "day": 1,
            "stops": [
                {"name": "Morning Gallery", "kind": "attraction", "time": "09:00"},
                {"name": "Coastal Walk", "kind": "attraction", "time": "11:00"},
            ],
        }]
        update_trip_plan.invoke({"updates_json": json.dumps({"day_wise_itinerary": original})})

        result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Cavelossim Beach", "kind": "attraction", "time": "10:00"},
                    {"name": "Basilica of Bom Jesus", "kind": "attraction", "time": "10:00"},
                    {"name": "Colva Beach", "kind": "attraction", "time": "09:30"},
                ],
            }],
        })})

        assert "times must increase in circuit order" in result
        assert "Basilica of Bom Jesus" in result
        assert json.loads(get_trip_plan.invoke({}))["day_wise_itinerary"] == original

        tight_result = update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {
                        "name": "Cavelossim Beach",
                        "kind": "attraction",
                        "time": "10:00",
                        "duration_min": 90,
                    },
                    {"name": "Colva Beach", "kind": "attraction", "time": "11:00"},
                ],
            }],
        })})

        assert "not before 12:00" in tight_result
        assert json.loads(get_trip_plan.invoke({}))["day_wise_itinerary"] == original

    def test_reflow_orders_fully_timed_stops_and_repairs_time_collisions(self, monkeypatch):
        from tripplanner.tools import trip_planner

        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_details",
            lambda _name, _destination: {"lat": 15.3, "lng": 73.9},
        )
        plan = {
            "destination": "Goa",
            "day_wise_itinerary": [{
                "day": 1,
                "stops": [
                    {"name": "Holiday Inn", "kind": "hotel"},
                    {"name": "Dinner", "kind": "meal", "time": "18:30", "duration_min": 60},
                    {"name": "Cavelossim Beach", "kind": "attraction", "time": "10:00", "duration_min": 90},
                    {"name": "Basilica", "kind": "attraction", "time": "10:00", "duration_min": 75},
                    {"name": "Colva Beach", "kind": "attraction", "time": "16:30", "duration_min": 90},
                    {"name": "Holiday Inn", "kind": "hotel"},
                ],
            }],
        }

        assert trip_planner._reflow_unbooked_attractions(plan) is True
        stops = plan["day_wise_itinerary"][0]["stops"]
        assert [stop["name"] for stop in stops] == [
            "Holiday Inn", "Cavelossim Beach", "Basilica", "Colva Beach", "Dinner", "Holiday Inn",
        ]
        times = [trip_planner._parse_hhmm(stop.get("time", "")) for stop in stops[1:-1]]
        assert all(left is not None and right is not None and left < right for left, right in zip(times, times[1:]))

    def test_set_stop_booked_toggles_flag(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Baga Beach", "kind": "attraction"}]},
            ],
        })})
        assert set_stop_booked(1, "Baga Beach", True) is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["day_wise_itinerary"][0]["stops"][0]["booked"] is True
        # toggling off persists too
        assert set_stop_booked(1, "baga beach", False) is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["day_wise_itinerary"][0]["stops"][0]["booked"] is False

    def test_remove_selection_drops_itinerary_only_place(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        # Place a stop directly in the itinerary WITHOUT adding it to a
        # selected_* bucket (mimics the agent weaving it into the plan).
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]},
            ],
        })})
        assert remove_selection("attraction", "Fort Aguada") is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["day_wise_itinerary"][0]["stops"] == []

    def test_remove_selection_clears_selected_bucket_and_itinerary(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "Fort Aguada"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]},
            ],
        })})

        assert remove_selection("attraction", "Fort Aguada") is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["selected_activities"] == []
        assert plan["day_wise_itinerary"][0]["stops"] == []

    def test_remove_selection_removes_only_requested_occurrence(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "Fort Aguada"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction", "time": "10:00"}]},
                {"day": 2, "stops": [{"name": "Fort Aguada", "kind": "attraction", "time": "16:00"}]},
            ],
        })})

        assert remove_selection(
            "attraction", "Fort Aguada", day=2, stop=1, all_occurrences=False
        ) is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["day_wise_itinerary"][0]["stops"][0]["time"] == "10:00"
        assert plan["day_wise_itinerary"][1]["stops"] == []
        assert plan["selected_activities"] == [{"name": "Fort Aguada"}]

    def test_remove_selection_last_occurrence_clears_selected_bucket(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "Fort Aguada"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Fort Aguada", "kind": "attraction"}]},
            ],
        })})

        assert remove_selection(
            "attraction", "Fort Aguada", day=1, stop=1, all_occurrences=False
        ) is True
        plan = json.loads(get_trip_plan.invoke({}))
        assert plan["selected_activities"] == []
        assert plan["day_wise_itinerary"][0]["stops"] == []

    def test_remove_selection_rejects_single_hotel_circuit_anchor(self):
        create_trip_plan.invoke({
            "destination": "London",
            "departure_date": "2026-08-26",
            "return_date": "2026-08-31",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "Wilde Aparthotels", "city": "London"}],
            "day_wise_itinerary": [
                {
                    "day": 4,
                    "stops": [
                        {"name": "Wilde Aparthotels", "kind": "hotel"},
                        {"name": "Kew Gardens", "kind": "attraction"},
                        {"name": "Wilde Aparthotels", "kind": "hotel"},
                    ],
                },
            ],
        })})

        assert remove_selection(
            "hotel", "Wilde Aparthotels", day=4, stop=1, all_occurrences=False
        ) is False
        plan = json.loads(get_trip_plan.invoke({}))
        assert [stop["name"] for stop in plan["day_wise_itinerary"][0]["stops"]] == [
            "Wilde Aparthotels",
            "Kew Gardens",
            "Wilde Aparthotels",
        ]

    def test_set_stop_booked_normalizes_string_stop(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{"day": 1, "stops": ["Anjuna Market"]}],
        })})
        assert set_stop_booked(1, "Anjuna Market", True) is True
        plan = json.loads(get_trip_plan.invoke({}))
        stop = plan["day_wise_itinerary"][0]["stops"][0]
        assert stop == {"name": "Anjuna Market", "booked": True}

    def test_set_stop_booked_unknown_returns_false(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        assert set_stop_booked(1, "Nowhere", True) is False

    def test_add_selection_infers_time_between_neighbor_stops(self):
        from tripplanner.tools.trip_planner import add_selection

        create_trip_plan.invoke({
            "destination": "Kolkata",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [
                        {"name": "Kaali Maa Pujo Pandal", "kind": "attraction", "time": "09:30"},
                        {"name": "Peter Cat", "kind": "meal", "time": "19:00"},
                    ],
                }
            ]
        })})

        res = add_selection("attraction", {"name": "Victoria Memorial"})
        assert res["ok"] is True
        plan = json.loads(get_trip_plan.invoke({}))
        stops = plan["day_wise_itinerary"][0]["stops"]
        vm = next(s for s in stops if str(s.get("name")) == "Victoria Memorial")
        assert vm.get("time") != ""
        assert vm.get("time") is not None

    def test_add_selection_keeps_explicit_itinerary_day(self, monkeypatch):
        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_details",
            lambda name, _destination: {
                "North Stay": {"lat": 15.60, "lng": 73.75},
                "South Stay": {"lat": 15.20, "lng": 74.00},
                "North Market": {"lat": 15.59, "lng": 73.76},
            }.get(name, {}),
        )
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "North Stay", "kind": "hotel"}]},
                {"day": 2, "stops": [{"name": "South Stay", "kind": "hotel"}]},
            ],
        })})

        result = add_selection(
            "attraction", {"name": "North Market"}, preferred_day=2
        )

        assert result["placement"] == {"day": 2, "stop": 2, "name": "North Market"}
        plan = json.loads(get_trip_plan.invoke({}))
        assert [stop["name"] for stop in plan["day_wise_itinerary"][0]["stops"]] == [
            "North Stay"
        ]
        assert [stop["name"] for stop in plan["day_wise_itinerary"][1]["stops"]] == [
            "South Stay",
            "North Market",
        ]

    def test_crowded_explicit_day_offers_review_without_moving_choice(self):
        from tripplanner.tools.trip_planner import assess_itinerary_change

        plan = {
            "destination": "Goa",
            "day_wise_itinerary": [{
                "day": 3,
                "stops": [
                    {"name": "Stay", "kind": "hotel"},
                    {"name": "Fort", "kind": "attraction", "duration_min": 90},
                    {"name": "Beach", "kind": "attraction", "duration_min": 90},
                    {"name": "Market", "kind": "attraction", "duration_min": 90},
                    {"name": "Museum", "kind": "attraction", "duration_min": 90},
                    {"name": "Dinner", "kind": "meal", "duration_min": 90},
                    {"name": "Stay", "kind": "hotel"},
                ],
            }],
        }

        review = assess_itinerary_change(
            plan,
            action="added",
            name="Museum",
            days=[3],
        )

        assert review is not None
        assert review["day"] == 3
        assert review["summary"].startswith("Day 3 may feel crowded")
        assert "Do not change the itinerary" in review["prompt"]
        assert [stop["name"] for stop in plan["day_wise_itinerary"][0]["stops"]][4] == "Museum"

    def test_direct_add_reports_exact_day_and_material_review(self):
        from tripplanner.web import trip_operations

        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{
                "day": 3,
                "stops": [
                    {"name": "Taj Cidade de Goa", "kind": "hotel"},
                    {"name": "Fort", "kind": "attraction"},
                    {"name": "Beach", "kind": "attraction"},
                    {"name": "Market", "kind": "attraction"},
                    {"name": "Dinner", "kind": "meal"},
                    {"name": "Taj Cidade de Goa", "kind": "hotel"},
                ],
            }],
        })})

        result = trip_operations.select("attraction", "Museum", day=3)

        assert result["alerts"][0] == "Added Museum to Day 3."
        assert result["placement"]["day"] == 3
        assert result["planner_review"]["day"] == 3

    def test_add_selection_places_restaurant_as_meal(self):
        create_trip_plan.invoke({
            "destination": "Paris",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-20",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{"day": 1, "stops": []}],
        })})

        result = add_selection("meal", {"name": "Le Comptoir"}, preferred_day=1)

        assert result["trip"]["day_wise_itinerary"][0]["stops"][0]["kind"] == "meal"

    def test_explicit_day_moves_existing_unbooked_stop(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": []},
                {"day": 2, "stops": [{"name": "North Market", "kind": "attraction"}]},
            ],
        })})

        result = add_selection("attraction", {"name": "North Market"}, preferred_day=1)

        assert result["ok"] is True
        assert result["placement"] == {"day": 1, "stop": 1, "name": "North Market"}
        assert result["trip"]["day_wise_itinerary"][0]["stops"][0]["name"] == "North Market"
        assert result["trip"]["day_wise_itinerary"][1]["stops"] == []

    def test_explicit_day_repositions_already_selected_stop(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "North Market"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": []},
                {"day": 2, "stops": [{"name": "North Market", "kind": "attraction"}]},
            ],
        })})

        result = add_selection("attraction", {"name": "North Market"}, preferred_day=1)

        assert result["ok"] is True
        assert result["placement"]["day"] == 1
        assert result["trip"]["day_wise_itinerary"][1]["stops"] == []

    def test_explicit_day_moves_only_requested_repeated_occurrence(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-22",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "North Market"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "North Market", "kind": "attraction"}]},
                {"day": 2, "stops": [{"name": "North Market", "kind": "attraction"}]},
                {"day": 3, "stops": []},
            ],
        })})

        result = add_selection(
            "attraction",
            {"name": "North Market"},
            preferred_day=3,
            source_day=2,
            source_stop=1,
        )

        assert result["ok"] is True
        assert result["placement"]["day"] == 3
        assert result["trip"]["day_wise_itinerary"][0]["stops"][0]["name"] == "North Market"
        assert result["trip"]["day_wise_itinerary"][1]["stops"] == []
        assert result["trip"]["day_wise_itinerary"][2]["stops"][0]["name"] == "North Market"

    def test_explicit_day_rejects_repeated_occurrence_collision(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-22",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [{"name": "North Market"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "North Market", "kind": "attraction"}]},
                {"day": 2, "stops": [{"name": "North Market", "kind": "attraction"}]},
            ],
        })})

        result = add_selection(
            "attraction",
            {"name": "North Market"},
            preferred_day=1,
            source_day=2,
            source_stop=1,
        )

        assert result["ok"] is False
        assert result["alerts"] == ["North Market is already on Day 1. Choose a different day."]
        assert [
            stop["name"]
            for day in result["trip"]["day_wise_itinerary"]
            for stop in day["stops"]
        ] == ["North Market", "North Market"]

    def test_explicit_unavailable_day_returns_alternatives_without_saving(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [{"day": 2, "stops": []}, {"day": 3, "stops": []}],
        })})

        result = add_selection("attraction", {"name": "North Market"}, preferred_day=1)

        assert result["ok"] is False
        assert "Choose Day 2, Day 3, or Best day" in result["alerts"][0]
        assert result["trip"].get("selected_activities") == []

    def test_explicit_day_does_not_move_booked_stop(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-09-18",
            "return_date": "2026-09-21",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": []},
                {"day": 2, "stops": [
                    {"name": "North Market", "kind": "attraction", "booked": True}
                ]},
            ],
        })})

        result = add_selection("attraction", {"name": "North Market"}, preferred_day=1)

        assert result["ok"] is False
        assert "booked on Day 2" in result["alerts"][0]
        assert "unbook it and choose Day 1 again" in result["alerts"][0]
        assert result["trip"]["day_wise_itinerary"][1]["stops"][0]["booked"] is True

    def test_add_hotel_stay_updates_range(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Old Stay", "kind": "hotel"}, {"name": "Fort Aguada", "kind": "attraction"}]},
                {"day": 2, "stops": [{"name": "Old Stay", "kind": "hotel"}, {"name": "Baga Beach", "kind": "attraction"}]},
                {"day": 3, "stops": [{"name": "Candolim", "kind": "attraction"}]},
            ],
        })})

        result = add_hotel_stay("Taj Goa", start_day=2, end_day=3, replace_existing=True)
        assert result["ok"] is True
        plan = json.loads(get_trip_plan.invoke({}))
        day2 = plan["day_wise_itinerary"][1]["stops"]
        day3 = plan["day_wise_itinerary"][2]["stops"]
        assert day2[0]["name"] == "Taj Goa"
        assert day2[0]["kind"] == "hotel"
        assert day3[0]["name"] == "Taj Goa"
        assert day3[0]["kind"] == "hotel"

    def test_add_hotel_stay_replacement_prunes_old_selected_hotel(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_hotels": [{"name": "ITC Goa"}],
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "ITC Goa", "kind": "hotel"}]},
                {"day": 2, "stops": [{"name": "ITC Goa", "kind": "hotel"}]},
            ],
        })})

        result = add_hotel_stay("Hyatt Goa", start_day=1, end_day=2, replace_existing=True)
        assert result["ok"] is True
        plan = json.loads(get_trip_plan.invoke({}))
        selected = [str(h.get("name") or "") for h in plan.get("selected_hotels") or [] if isinstance(h, dict)]
        assert "Hyatt Goa" in selected
        assert "ITC Goa" not in selected

    def test_hotel_replacement_reflows_unbooked_attractions_by_proximity(self, monkeypatch):
        coords = {
            "North Stay": {"lat": 15.60, "lng": 73.75},
            "South Stay": {"lat": 15.20, "lng": 74.00},
            "North Beach": {"lat": 15.59, "lng": 73.76},
            "South Fort": {"lat": 15.21, "lng": 73.99},
        }
        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_details",
            lambda name, _destination: coords.get(name, {}),
        )
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-03",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [
                    {"name": "North Stay", "kind": "hotel"},
                    {"name": "South Fort", "kind": "attraction"},
                ]},
                {"day": 2, "stops": [
                    {"name": "South Stay", "kind": "hotel"},
                    {"name": "North Beach", "kind": "attraction"},
                ]},
            ],
        })})

        result = add_hotel_stay("North Stay", start_day=1, end_day=1, replace_existing=True)
        assert result["ok"] is True
        plan = json.loads(get_trip_plan.invoke({}))
        day1 = [_stop["name"] for _stop in plan["day_wise_itinerary"][0]["stops"]]
        day2 = [_stop["name"] for _stop in plan["day_wise_itinerary"][1]["stops"]]
        assert day1 == ["North Stay", "North Beach"]
        assert day2 == ["South Stay", "South Fort"]

    def test_itinerary_reflow_keeps_booked_attraction_on_its_day(self, monkeypatch):
        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_details",
            lambda *_args: {"lat": 15.5, "lng": 73.8},
        )
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-03",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {
                    "day": 1,
                    "stops": [{"name": "Taj Cidade de Goa", "kind": "hotel"}],
                },
                {"day": 2, "stops": [
                    {"name": "Booked Tour", "kind": "attraction", "booked": True},
                    {"name": "Flexible Stop", "kind": "attraction"},
                ]},
            ],
        })})

        add_hotel_stay("New Stay", start_day=1, end_day=2, replace_existing=True)
        plan = json.loads(get_trip_plan.invoke({}))
        day2 = plan["day_wise_itinerary"][1]["stops"]
        assert any(stop.get("name") == "Booked Tour" and stop.get("booked") for stop in day2)

    def test_attraction_add_and_remove_reflow_all_days(self, monkeypatch):
        coords = {
            "North Stay": {"lat": 15.60, "lng": 73.75},
            "South Stay": {"lat": 15.20, "lng": 74.00},
            "North Beach": {"lat": 15.59, "lng": 73.76},
            "North Market": {"lat": 15.58, "lng": 73.77},
            "South Fort": {"lat": 15.21, "lng": 73.99},
        }
        monkeypatch.setattr(
            "tripplanner.tools.trip_planner.places_cache.get_details",
            lambda name, _destination: coords.get(name, {}),
        )
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-03",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "selected_activities": [
                {"name": "North Beach"},
                {"name": "South Fort"},
            ],
            "day_wise_itinerary": [
                {"day": 1, "stops": [
                    {"name": "North Stay", "kind": "hotel"},
                    {"name": "South Fort", "kind": "attraction"},
                ]},
                {"day": 2, "stops": [
                    {"name": "South Stay", "kind": "hotel"},
                    {"name": "North Beach", "kind": "attraction"},
                ]},
            ],
        })})

        add_selection("attraction", {"name": "North Market"})
        plan = json.loads(get_trip_plan.invoke({}))
        day1_names = [_stop["name"] for _stop in plan["day_wise_itinerary"][0]["stops"]]
        day2_names = [_stop["name"] for _stop in plan["day_wise_itinerary"][1]["stops"]]
        assert day1_names == ["North Stay", "North Beach", "North Market"]
        assert day2_names == ["South Stay", "South Fort"]

        assert remove_selection("attraction", "North Beach") is True
        plan = json.loads(get_trip_plan.invoke({}))
        day1_names = [_stop["name"] for _stop in plan["day_wise_itinerary"][0]["stops"]]
        day2_names = [_stop["name"] for _stop in plan["day_wise_itinerary"][1]["stops"]]
        assert day1_names == ["North Stay", "North Market"]
        assert day2_names == ["South Stay", "South Fort"]

    def test_add_second_hotel_spreads_instead_of_refreshing_first(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        update_trip_plan.invoke({"updates_json": json.dumps({
            "day_wise_itinerary": [
                {"day": 1, "stops": [{"name": "Hotel One", "kind": "hotel"}, {"name": "Baga Beach", "kind": "attraction"}]},
                {"day": 2, "stops": [{"name": "Anjuna Market", "kind": "attraction"}]},
            ],
        })})

        add_selection("hotel", {"name": "Hotel One"})
        add_selection("hotel", {"name": "Hotel Two"})
        plan = json.loads(get_trip_plan.invoke({}))
        day1_names = [
            (s.get("name") if isinstance(s, dict) else str(s))
            for s in plan["day_wise_itinerary"][0]["stops"]
        ]
        day2_names = [
            (s.get("name") if isinstance(s, dict) else str(s))
            for s in plan["day_wise_itinerary"][1]["stops"]
        ]
        assert "Hotel One" in day1_names
        assert "Hotel Two" in day2_names

    def test_finalize_trip(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            selected_flights=[{"airline": "IndiGo", "price": 8500}]
        )

        result = finalize_trip.invoke({})

        assert "FINALIZED" in result
        assert "IndiGo" in result

    def test_finalize_requires_selections(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        result = finalize_trip.invoke({})
        assert "Cannot finalize" in result

    def test_finalize_blocks_missing_return_coverage(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            origin="Delhi",
            travel_scope="round_trip",
            return_date="2026-07-07",
            selected_flights=[{"airline": "IndiGo", "price": 8500}],
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {
                            "name": "Flight Delhi to Goa",
                            "kind": "flight",
                            "time": "08:00",
                            "duration_min": 120,
                        },
                        {"name": "Taj Goa", "kind": "hotel", "time": "11:00"},
                        {"name": "Riverside Walk", "kind": "attraction", "time": "13:00"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Taj Goa", "kind": "hotel", "time": "09:00"},
                        {"name": "Old Goa Walk", "kind": "attraction", "time": "11:00"},
                    ],
                },
            ],
        )

        result = finalize_trip.invoke({})

        assert "Cannot finalize" in result
        assert "Goa back to Delhi" in result
        assert json.loads(get_trip_plan.invoke({}))["status"] == "draft"

    def test_finalize_blocks_activity_after_departure(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            origin="Delhi",
            travel_scope="round_trip",
            return_date="2026-07-07",
            selected_flights=[{"airline": "IndiGo", "price": 8500}],
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {
                            "name": "Flight Delhi to Goa",
                            "kind": "flight",
                            "time": "08:00",
                            "duration_min": 120,
                        },
                        {"name": "Taj Goa", "kind": "hotel", "time": "11:00"},
                        {"name": "Riverside Walk", "kind": "attraction", "time": "13:00"},
                    ],
                },
                {
                    "day": 2,
                    "stops": [
                        {"name": "Taj Goa", "kind": "hotel", "time": "08:00"},
                        {
                            "name": "Flight Goa to Delhi",
                            "kind": "flight",
                            "time": "14:00",
                            "duration_min": 120,
                        },
                        {"name": "Old Goa Walk", "kind": "attraction", "time": "17:00"},
                    ],
                },
            ],
        )

        result = finalize_trip.invoke({})

        assert "Cannot finalize" in result
        assert "Old Goa Walk" in result
        assert "after Flight Goa to Delhi" in result

    def test_finalize_blocks_known_closed_day(self, monkeypatch):
        def closed_monday(name, _destination):
            if name == "Closed Museum":
                return {
                    "name": name,
                    "weekday_descriptions": ["Monday: Closed"],
                }
            return {}

        monkeypatch.setattr(
            "tripplanner.tools.trip_guard._summary_for_place",
            closed_monday,
        )
        self._save_booking_ready_trip(
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {"name": "Taj Goa", "kind": "hotel", "time": "09:00"},
                        {"name": "Closed Museum", "kind": "attraction", "time": "11:00"},
                    ],
                }
            ]
        )

        result = finalize_trip.invoke({})

        assert "Cannot finalize" in result
        assert "Closed Museum is closed on Mondays" in result

    def test_finalize_blocks_placeholder_lodging(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {"name": "Hotel option", "kind": "hotel", "time": "09:00"},
                        {
                            "name": "Riverside Walk",
                            "kind": "attraction",
                            "time": "11:00",
                        },
                    ],
                }
            ]
        )

        result = finalize_trip.invoke({})

        assert "Cannot finalize" in result
        assert "Hotel placeholders remain on Day(s) 1" in result

    def test_finalize_keeps_unknown_place_facts_silent(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip()

        result = finalize_trip.invoke({})

        assert "FINALIZED" in result

    def test_execute_bookings(self, monkeypatch):
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            selected_flights=[{"airline": "IndiGo", "price": 8500}]
        )
        finalize_trip.invoke({})
        result = execute_bookings.invoke({})
        assert "All bookings executed" in result
        assert "No active trip plan" in get_trip_plan.invoke({})

    def test_execute_requires_finalized(self):
        create_trip_plan.invoke({
            "destination": "Goa",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-05",
        })
        result = execute_bookings.invoke({})
        assert "must be finalized" in result

    def test_list_past_trips_empty(self):
        result = list_past_trips.invoke({})
        assert "No past trips" in result

    def test_full_lifecycle(self, monkeypatch):
        """Test the complete plan → finalize → execute → history cycle."""
        monkeypatch.setattr("tripplanner.tools.trip_guard._summary_for_place", lambda *_: {})
        self._save_booking_ready_trip(
            destination="Manali",
            selected_hotels=[{"name": "Snow Valley", "city": "Manali", "price": 12000}],
            selected_activities=[{"name": "Rohtang Pass", "price": 2000}],
            day_wise_itinerary=[
                {
                    "day": 1,
                    "stops": [
                        {"name": "Snow Valley", "kind": "hotel", "time": "09:00"},
                        {"name": "Rohtang Pass", "kind": "attraction", "time": "11:00"},
                    ],
                }
            ],
            cost_breakdown={"hotel": 12000, "activities": 2000},
            total_cost=14000,
        )
        # Finalize
        result = finalize_trip.invoke({})
        assert "FINALIZED" in result
        # Execute
        result = execute_bookings.invoke({})
        assert "All bookings executed" in result
        # Check history
        result = list_past_trips.invoke({})
        assert "manali" in result.lower()
