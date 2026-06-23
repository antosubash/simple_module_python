"""FastAPI dependencies for the Branding module."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from branding.service import BrandingService


async def get_branding_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BrandingService:
    return BrandingService(request.app, db)


BrandingServiceDep = Annotated[BrandingService, Depends(get_branding_service)]
