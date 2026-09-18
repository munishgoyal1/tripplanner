"""Compatibility alias for tripplanner.harness.audit_report."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("tripplanner.harness.audit_report")
