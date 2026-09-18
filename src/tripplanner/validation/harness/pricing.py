"""Compatibility alias for tripplanner.pricing."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.pricing")
