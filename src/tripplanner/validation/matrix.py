"""Compatibility alias for tripplanner.harness.generation.matrix."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.harness.generation.matrix")
