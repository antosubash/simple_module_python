"""Detect system settings that still use the pre-mail-module namespace."""

from simple_module_core.data_compatibility import DataCompatibilityIssue
from simple_module_db.stored_settings import (
    SCOPE_SYSTEM,
    SYSTEM_SCOPE_ID,
    settings_table_clause,
    settings_table_exists,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mail.constants import LEGACY_MAIL_KEYS, UPGRADE_SETTINGS_NAMESPACE


async def check_data_compatibility(db: AsyncSession) -> list[DataCompatibilityIssue]:
    if not await settings_table_exists(db):
        return []
    settings = settings_table_clause()
    found = await db.scalar(
        select(settings.c.key)
        .where(
            settings.c.scope == SCOPE_SYSTEM,
            settings.c.scope_id == SYSTEM_SCOPE_ID,
            settings.c.key.in_(LEGACY_MAIL_KEYS),
        )
        .limit(1)
    )
    if found is None:
        return []
    return [
        DataCompatibilityIssue(
            upgrade_id=UPGRADE_SETTINGS_NAMESPACE,
            message="Obsolete system users.mailer/SMTP settings must move to mail.*; "
            "target values win.",
            severity="warning",
        )
    ]
