"""The combined host settings object: ``HostSettings`` (DB-backed) + ``BootstrapSettings`` (env).

``Settings`` is the type most of the host and its tests use. Code that needs only
the process-wiring half or only the DB-backed half may depend on
``BootstrapSettings`` / ``HostSettings`` directly; this is not a deprecated shim.
"""

from __future__ import annotations

from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings


class Settings(HostSettings, BootstrapSettings):
    """Combined bootstrap + host settings."""
