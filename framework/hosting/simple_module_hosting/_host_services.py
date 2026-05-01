"""``_HostServices`` container exposed on ``app.state.host``.

Module-scope so the type is stable across ``create_app`` calls — tests
that build multiple apps in one process can ``isinstance``-check
``app.state.host`` against the same class object.
"""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_hosting.host_settings import HostSettings

__all__ = ["_HostServices"]


@dataclass
class _HostServices:
    """Container for host-level services exposed on ``app.state.host``."""

    settings: HostSettings
