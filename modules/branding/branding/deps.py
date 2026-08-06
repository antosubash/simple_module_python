"""FastAPI dependencies for the Branding module."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from file_storage.deps import get_file_storage_service
from file_storage.service import FileStorageService
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from branding.service import BrandingService


async def get_branding_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
    storage: FileStorageService = Depends(get_file_storage_service),
) -> BrandingService:
    # FastAPI caches dependencies per request, so ``storage`` shares this very
    # session: reaping a replaced image commits or rolls back with the settings
    # write rather than in a transaction of its own.
    return BrandingService(request.app, db, storage)


BrandingServiceDep = Annotated[BrandingService, Depends(get_branding_service)]
