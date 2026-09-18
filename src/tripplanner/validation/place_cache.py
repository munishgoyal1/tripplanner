"""Compatibility alias for tripplanner.harness.sources.place_cache."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.harness.sources.place_cache")
