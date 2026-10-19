"""FastAPI dependencies for the file_storage module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.events import EventBus
from simple_module_core.permissions import grants
from simple_module_db.deps import get_db
from simple_module_db.listeners import current_user_id
from simple_module_hosting.permissions import ensure_resolved_permissions
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage import constants
from file_storage.service import FileStorageService
from file_storage.services import FileStorageServices

# Matches no row: ``created_by`` is a user id or NULL, never the empty string.
NO_OWNER = ""


async def get_file_storage_services(request: Request) -> FileStorageServices:
    return request.app.state.file_storage


async def get_file_storage_service(
    db: AsyncSession = Depends(get_db),
    services: FileStorageServices = Depends(get_file_storage_services),
) -> FileStorageService:
    return FileStorageService(db, services.backend, services.settings, services.aggregates)


async def get_owner_scope(request: Request) -> str | None:
    """Whose files this request may see and change (#544).

    ``None`` — every file in the active tenant — for a caller holding
    ``file_storage.manage`` (platform admins via the wildcard, organisation
    admins and owners). Anyone else is confined to the rows they uploaded: the
    id is read from the same ``current_user_id`` the audit listener stamps
    ``created_by`` with, so the two cannot disagree. A principal with no id
    gets :data:`NO_OWNER`, which matches nothing rather than everything.

    Endpoints hand the result to the service, which applies it in the query —
    so another user's file misses exactly like an unknown id (404, not 403).
    Internal callers (branding, reapers, tasks) never pass it and stay
    unscoped.
    """
    if grants(await ensure_resolved_permissions(request), constants.Permission.MANAGE):
        return None
    return current_user_id.get() or NO_OWNER


async def get_event_bus(request: Request) -> EventBus:
    return request.app.state.sm.event_bus
