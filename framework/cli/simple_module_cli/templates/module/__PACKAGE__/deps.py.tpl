"""FastAPI dependencies for the {{MODULE_NAME}} module."""

from __future__ import annotations

from fastapi import Depends
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from {{PACKAGE_NAME}}.service import {{SINGULAR_CLASS}}Service


async def get_{{SINGULAR}}_service(
    db: AsyncSession = Depends(get_db),
) -> {{SINGULAR_CLASS}}Service:
    return {{SINGULAR_CLASS}}Service(db)
