"""Moved to :mod:`background_tasks.outbox.transport`; this alias goes in 0.0.46 (module layout)."""

from __future__ import annotations

import importlib
import sys

from simple_module_core.deprecation import deprecated_module

deprecated_module(
    "background_tasks.outbox_transport",
    remove_in="0.0.46",
    use="background_tasks.outbox.transport",
)
sys.modules[__name__] = importlib.import_module("background_tasks.outbox.transport")
