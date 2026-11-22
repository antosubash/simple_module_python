"""Trusted public origins for links, independent of the inbound Host header."""

from __future__ import annotations

from simple_module_hosting.config.host_settings import HostSettings


def public_origin(settings: HostSettings | None, override: str = "") -> str:
    """Explicit module origin → host origin → relative links (fresh installs)."""
    return (override.strip() or (settings.public_base_url if settings else "")).rstrip("/")
