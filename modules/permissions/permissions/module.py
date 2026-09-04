"""Permissions module definition."""

from __future__ import annotations

import ast
import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from permissions.constants import _MODULE_AUTH, _MODULE_USERS

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession


async def _resolve_role_permission_labels(_db: AsyncSession, ids: list[str]) -> dict[str, str]:
    """Render a composite primary key as "admin · settings.create".

    ``RolePermission`` is keyed on ``(role_name, permission_key)``, and the
    audit trail records a composite key as ``str(tuple)`` — so the cell was
    rendering a Python tuple repr, quotes and all. Both halves are already in
    the id, so this needs no query: it parses the repr the recorder wrote and
    joins it the way the rest of the product writes the pair.
    """
    labels: dict[str, str] = {}
    for raw in ids:
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            continue
        if isinstance(parsed, tuple) and all(isinstance(part, str) for part in parsed):
            labels[raw] = " · ".join(parsed)
    return labels


class PermissionsModule(ModuleBase):
    meta = ModuleMeta(
        name="Permissions",
        route_prefix="/api/permissions",
        view_prefix="/admin/permissions",
        depends_on=[_MODULE_AUTH, _MODULE_USERS],
        i18n_audience="admin",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from permissions.endpoints.api import router as api
        from permissions.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        """Name role-grant rows, and tag them with their table.

        No ``url_template``: a role/permission pair is a join row with no
        screen of its own — the role editor edits the whole role at once — so
        the audit cell renders the pair unlinked.
        """
        from permissions.models import RolePermission

        registry.register(
            AuditLink(
                # Class name, not __tablename__ — see AuditLink.entity_type.
                entity_type=RolePermission.__name__,
                url_template="",
                label="Role permission",
                label_key="permissions.audit.role_permission",
                table_name=RolePermission.__tablename__,
                label_resolver=_resolve_role_permission_labels,
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        from permissions.constants import PERM_MANAGE, PERM_VIEW, PERMISSION_GROUP

        registry.add_group(
            PERMISSION_GROUP,
            [PERM_VIEW, PERM_MANAGE],
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {"permissions": base}

    async def on_startup(self, app: FastAPI) -> None:
        """Replay persisted role→permission rows into the live registry."""
        from permissions.service import PermissionService

        db_state = app.state.sm.db
        registry = app.state.sm.permissions
        async with db_state.session_factory() as db:
            service = PermissionService(db, registry)
            await service.load_all_into_registry()
            await service.sync_admin_all_permissions()
            await db.commit()
