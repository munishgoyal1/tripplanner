"""Compatibility alias for tripplanner.evals.human."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.evals.human")
