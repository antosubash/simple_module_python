"""audit_log settings — DB-backed via ``register_module_settings``."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from simple_module_core.settings_base import DbBackedSettings


class AuditLogSettings(DbBackedSettings):
    """Configuration for the audit trail."""

    model_config = SettingsConfigDict(extra="ignore")

    refuse_unaudited_dml: bool = Field(default=False)
    """Raise on an ``execution_options(sm_audit=False)`` write to an audited model (#557).

    Off by default. On, statement DML against an audited model can no longer
    opt out of the trail; ``text()`` writes still need ``record_bulk_audit``.
    """
