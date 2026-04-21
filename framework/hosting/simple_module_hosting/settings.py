"""Back-compat shim — prefer BootstrapSettings + HostSettings directly."""

from __future__ import annotations

from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings


class Settings(HostSettings, BootstrapSettings):
    """Combined bootstrap + host settings for legacy import sites."""
