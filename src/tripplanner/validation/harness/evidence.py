"""Compatibility alias for tripplanner.harness.evidence."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.harness.evidence")
