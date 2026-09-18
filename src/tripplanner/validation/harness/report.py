"""Compatibility alias for tripplanner.harness.report."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.harness.report")
