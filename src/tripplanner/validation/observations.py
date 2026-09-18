"""Compatibility alias for tripplanner.evals.observations."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.evals.observations")
