"""Module-scoped state container, stored as ``app.state.audit_log``."""

from __future__ import annotations

from dataclasses import dataclass

from audit_log.settings import AuditLogSettings


@dataclass
class AuditLogServices:
    """audit_log singletons. ``settings`` is swapped on a settings save."""

    settings: AuditLogSettings
