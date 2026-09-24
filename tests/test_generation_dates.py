from __future__ import annotations

import re
from datetime import date

from tripplanner.harness.generation import india_heuristic_matrix, india_outbound_matrix, matrix
from tripplanner.harness.generation.catalog import Catalog

_RANGE = re.compile(r"(\d{1,2})(?: ([A-Z][a-z]+))? to (\d{1,2}) ([A-Z][a-z]+) (\d{4})")


_MONTHS = {date(2027, month, 1).strftime("%B"): month for month in range(1, 13)}


def _span(message: str) -> int:
    match = _RANGE.search(message)
    assert match, message
    start_day, start_month, end_day, end_month, year = match.groups()
    start = date(int(year), _MONTHS[start_month or end_month], int(start_day))
    end = date(int(year), _MONTHS[end_month], int(end_day))
    return (end - start).days + 1


def test_generated_requests_span_exactly_their_day_count() -> None:
    """An N-day request named N+1 calendar dates, and the planner then kept a
    hotel night after the journey home (BL-04)."""
    for module in (matrix, india_heuristic_matrix, india_outbound_matrix):
        for request in module.candidates(Catalog(), limit=40):
            if request.days:
                assert _span(request.message) == request.days, request.message
