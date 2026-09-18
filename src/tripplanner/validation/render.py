"""Compatibility alias for tripplanner.evals.deterministic.render."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.evals.deterministic.render")
