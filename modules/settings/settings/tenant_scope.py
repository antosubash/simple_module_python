"""Guards for TENANT-scope writes (#382).

Two surfaces write tenant-scope rows, and they trust different things:

* the **platform** routes (``/api/settings/tenant/{scope_id}/…``, guarded by
  ``settings.*``) take the tenant from the URL, because a platform operator
  legitimately edits any tenant. The id must name a real tenant
  (:func:`require_known_tenant`) — a typo used to create a row no tenant would
  ever read.
* the **self-service** routes (``/api/settings/tenant/current/…``, guarded by
  ``settings.tenant.edit``) take the tenant from ``request.state.tenant_id``
  only (:func:`active_tenant`), and only for keys declared
  ``tenant_overridable`` (:func:`overridable_definition`).

A key with an ``clear_via`` cannot be deleted by a generic route while its
tenant exists (:func:`refuse_managed_key_delete`): the upload route reaps the file.

Both run the definition's ``check`` (:func:`run_check`) before writing.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from simple_module_core.tenancy import tenant_exists

from settings.constants import (
    ERR_MANAGED_KEY_DELETE,
    ERR_NO_ACTIVE_TENANT,
    ERR_NOT_TENANT_OVERRIDABLE,
    ERR_UNKNOWN_TENANT,
    MODULE_PACKAGE,
    STATUS_FORBIDDEN,
    STATUS_NOT_FOUND,
    STATUS_UNPROCESSABLE,
)
from settings.contracts.registry import SettingDefinition, SettingsRegistry
from settings.contracts.schemas import SettingOut, SettingScope
from settings.service import SettingService


def registry_of(request: Request) -> SettingsRegistry | None:
    services = getattr(request.app.state, MODULE_PACKAGE, None)
    return getattr(services, "registry", None)


async def is_known_tenant(request: Request, tenant_id: str) -> bool:
    """False only when a tenant-owning module says the id is unknown.

    With no such module installed (``tenant_exists`` answers ``None``) every id
    is accepted, which is the pre-#382 behaviour single-tenant installs rely on.
    """
    return await tenant_exists(request.app, tenant_id) is not False


async def require_known_tenant(request: Request, tenant_id: str) -> None:
    if not await is_known_tenant(request, tenant_id):
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail=ERR_UNKNOWN_TENANT)


def active_tenant(request: Request) -> str:
    """The request's resolved tenant; 403 when it acts for none."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=STATUS_FORBIDDEN, detail=ERR_NO_ACTIVE_TENANT)
    return tenant_id


def overridable_definition(request: Request, key: str) -> SettingDefinition:
    """The key's definition when a tenant may override it; 422 otherwise."""
    registry = registry_of(request)
    definition = registry.get(key) if registry is not None else None
    if definition is None or not definition.tenant_overridable:
        raise HTTPException(status_code=STATUS_UNPROCESSABLE, detail=ERR_NOT_TENANT_OVERRIDABLE)
    return definition


def refuse_managed_key_delete(request: Request, key: str) -> None:
    """422 when ``key`` is a file set by upload, naming the route that clears it.

    A bare row delete would leave the stored file behind, so the owner of the
    upload route (``SettingDefinition.clear_via``) is the only one to clear
    it — that is where the file is reaped.
    """
    registry = registry_of(request)
    definition = registry.get(key) if registry is not None else None
    if definition is not None and definition.clear_via:
        detail = ERR_MANAGED_KEY_DELETE.format(clear_via=definition.clear_via)
        raise HTTPException(status_code=STATUS_UNPROCESSABLE, detail=detail)


async def refuse_managed_key_delete_for_tenant(request: Request, tenant_id: str, key: str) -> None:
    """:func:`refuse_managed_key_delete` for platform routes that name the tenant.

    Only while the tenant still exists. A row left behind by a deleted tenant
    has no live owner to clear it through the upload route (and no file the
    tenant's reaper still tracks), so the operator may delete it by hand.
    """
    if await is_known_tenant(request, tenant_id):
        refuse_managed_key_delete(request, key)


async def refuse_tenant_managed_row_delete(
    request: Request, service: SettingService, setting_id: int
) -> None:
    """The by-id delete routes: refuse when the row is a live tenant's upload key."""
    row = await service.get_by_id(setting_id)
    if row is not None and row.scope == SettingScope.TENANT:
        await refuse_managed_key_delete_for_tenant(request, row.scope_id, row.key)


async def run_check(request: Request, tenant_id: str, key: str, value: str) -> None:
    """Run the key's declared ``check`` for a write at ``tenant_id``, if any."""
    registry = registry_of(request)
    definition = registry.get(key) if registry is not None else None
    if definition is None or definition.check is None:
        return
    try:
        await definition.check(request, tenant_id, value)
    except LookupError as exc:
        raise HTTPException(status_code=STATUS_NOT_FOUND, detail=str(exc) or key) from exc
    except ValueError as exc:
        raise HTTPException(status_code=STATUS_UNPROCESSABLE, detail=str(exc) or key) from exc


async def tenant_write_error(request: Request, tenant_id: str, key: str, value: str) -> str | None:
    """The reason a platform form may not write ``key`` at ``tenant_id``, or ``None``.

    For the Inertia store form, which reports errors on the field rather than
    as an HTTP status.
    """
    if not await is_known_tenant(request, tenant_id):
        return ERR_UNKNOWN_TENANT
    try:
        await run_check(request, tenant_id, key, value)
    except HTTPException as exc:
        return str(exc.detail)
    return None


async def tenant_update_error(
    request: Request, current: SettingOut | None, value: str | None
) -> str | None:
    """:func:`tenant_write_error` for the edit form (``PUT /settings/{id}``).

    The row's own scope, tenant and key decide — an update cannot move a row.
    Only a TENANT row whose value actually changes is checked: a
    description-only edit, or the masked echo of an unchanged secret, writes
    nothing the check could object to.
    """
    if current is None or current.scope != SettingScope.TENANT:
        return None
    if value is None or value == current.value:
        return None
    return await tenant_write_error(request, current.scope_id, current.key, value)


__all__ = [
    "active_tenant",
    "is_known_tenant",
    "overridable_definition",
    "refuse_managed_key_delete",
    "refuse_managed_key_delete_for_tenant",
    "refuse_tenant_managed_row_delete",
    "registry_of",
    "require_known_tenant",
    "run_check",
    "tenant_update_error",
    "tenant_write_error",
]
