"""Module-scope ``_HostServices`` container exposed on ``app.state.host``.

Lives in its own file so the dataclass type is stable across
``create_app`` calls (tests that build multiple apps in one process can
``isinstance(services, _HostServices)`` without each call minting a fresh
class) and so ``app_builder.py`` stays under the per-file line cap.
"""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_hosting.host_settings import HostSettings

__all__ = ["_HostServices"]


@dataclass
class _HostServices:
    """Container for host-level services exposed on ``app.state.host``."""

    settings: HostSettings
