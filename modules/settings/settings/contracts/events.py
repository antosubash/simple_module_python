"""Domain events published by the Settings module."""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class SettingsReloaded(Event):
    """Fired after a module's BaseSettings has been reloaded from the DB.

    Subscribers that cached stateful handles built from settings (SMTP client,
    Celery app config, middleware) can rebuild when ``package`` matches their
    own.
    """

    package: str
    changed: tuple[str, ...]
