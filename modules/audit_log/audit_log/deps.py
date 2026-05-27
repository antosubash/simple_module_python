"""FastAPI dependencies for the Audit Log module."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from audit_log.service import AuditLogService


async def get_audit_log_service(
    db: AsyncSession = Depends(get_db),
) -> AuditLogService:
    return AuditLogService(db)


AuditLogServiceDep = Annotated[AuditLogService, Depends(get_audit_log_service)]
