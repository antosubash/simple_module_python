"""Module-scoped state container.

Stored as ``app.state.{{PACKAGE_NAME}}`` by
:meth:`{{MODULE_NAME}}Module.register_settings`.

Not frozen — ``on_startup`` may set fields that depend on the DB or
other framework services. Convention: set once during boot, treat as
read-only after.
"""

from __future__ import annotations

from dataclasses import dataclass

from {{PACKAGE_NAME}}.settings import {{MODULE_NAME}}Settings


@dataclass
class {{MODULE_NAME}}Services:
    """{{MODULE_NAME}} module singletons."""

    settings: {{MODULE_NAME}}Settings
