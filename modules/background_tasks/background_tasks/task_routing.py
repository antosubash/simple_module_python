"""Moved to :mod:`background_tasks.worker.task_routing`;
this alias goes in 0.0.46 (module layout).
"""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module(
    "background_tasks.task_routing",
    remove_in="0.0.46",
    use="background_tasks.worker.task_routing",
)
sys.modules[__name__] = importlib.import_module("background_tasks.worker.task_routing")
