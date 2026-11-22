"""Host settings and their compiled request policy, swapped on hydration/reload."""

from __future__ import annotations

from simple_module_hosting.config.host_settings import HostSettings
from simple_module_hosting.pipeline._request_policy import RequestGuardPolicy

__all__ = ["_HostServices"]


class _HostServices:
    def __init__(self, settings: HostSettings) -> None:
        self.settings = settings

    @property
    def settings(self) -> HostSettings:
        return self._current[0]

    @settings.setter
    def settings(self, settings: HostSettings) -> None:
        # Compile before publishing: a failure leaves the previous pair intact.
        self._current = (settings, RequestGuardPolicy.from_settings(settings))

    @property
    def request_guards(self) -> RequestGuardPolicy:
        return self._current[1]
