"""FastAPI dependencies for the sharing module."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from simple_module_core.user_directory import get_user_directory
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from sharing.audience import Audience
from sharing.service import SharingError, SharingService


async def get_sharing_service(
    request: Request, db: AsyncSession = Depends(get_db)
) -> SharingService:
    return SharingService(
        db,
        request.app.state.sm.resource_types,
        get_user_directory(request.app),
        Audience(request.app, db),
    )


SharingServiceDep = Annotated[SharingService, Depends(get_sharing_service)]


def http_error(exc: SharingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)
