"""FastAPI dependencies for the file_storage module."""

from __future__ import annotations

from fastapi import Depends, Request
from simple_module_core.access.file_access import file_access_policies
from simple_module_core.access.permissions import grants
from simple_module_core.eventing.events import EventBus
from simple_module_db.deps import get_db
from simple_module_db.listeners import current_user_id
from simple_module_hosting.permissions import ensure_resolved_permissions
from simple_module_hosting.resource_deps import resource_principal
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage.core import constants
from file_storage.core.services import FileStorageServices
from file_storage.files.service import FileStorageService

# Matches no row: ``created_by`` is a user id or NULL, never the empty string.
NO_OWNER = ""


async def get_file_storage_services(request: Request) -> FileStorageServices:
    return request.app.state.file_storage


async def get_file_storage_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
    services: FileStorageServices = Depends(get_file_storage_services),
) -> FileStorageService:
    if services.backend is None:
        raise RuntimeError("file_storage backend is not initialised (on_startup has not run)")
    return FileStorageService(
        db,
        services.backend,
        services.settings,
        services.aggregates,
        policies=file_access_policies(request.app),
    )


async def get_owner_scope(request: Request) -> str | None:
    """Legacy uploader scope for browse controls (#544).

    Managers get the tenant uploader filter and quota ceiling; other callers
    cannot widen their scope through a query parameter. Use the same audit
    identity that stamps created_by, with an empty no-match value when absent.
    Actual row visibility is enforced by the authorized service's FileAccess
    policy, which can additionally admit module reviewers (#999).
    """
    if grants(await ensure_resolved_permissions(request), constants.Permission.MANAGE):
        return None
    return current_user_id.get() or NO_OWNER


OwnerScope = Depends(get_owner_scope)


async def get_event_bus(request: Request) -> EventBus:
    return request.app.state.sm.event_bus


async def get_authorized_file_storage_service(
    request: Request,
    service: FileStorageService = Depends(get_file_storage_service),
) -> FileStorageService:
    """Request-scoped access on generic routes; internal callers stay trusted."""
    return FileStorageService(
        service.db,
        service.backend,
        service.settings,
        service._aggregate_cache,
        policies=service.policies,
        principal=await resource_principal(request),
    )
