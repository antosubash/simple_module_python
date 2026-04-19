"""FastAPI dependencies for the Settings module."""

from __future__ import annotations

from fastapi import Depends
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from settings.service import SettingService


async def get_setting_service(
    db: AsyncSession = Depends(get_db),
) -> SettingService:
    return SettingService(db)
