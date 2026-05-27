"""Audit callback that converts AuditRecords into AuditEntry rows."""

from __future__ import annotations

import logging

from simple_module_db.audit import AuditRecord
from sqlalchemy.orm import Session

from audit_log.models import AuditEntry

logger = logging.getLogger(__name__)


def audit_callback(session: Session, records: list[AuditRecord]) -> None:
    try:
        for record in records:
            entry = AuditEntry(
                entity_type=record.entity_type,
                entity_id=record.entity_id,
                action=record.action,
                changes=record.changes,
                user_id=record.user_id,
                correlation_id=record.correlation_id,
            )
            session.add(entry)
    except Exception:
        logger.exception("Failed to write audit entries")
