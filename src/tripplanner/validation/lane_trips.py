"""Compatibility alias for tripplanner.harness.sources.lane_trips."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.harness.sources.lane_trips")
