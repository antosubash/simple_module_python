"""file_storage module — pluggable object storage with filesystem + S3 backends."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from simple_module_core.body_limits import BodyLimitRegistry
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_core.tenancy import TenantRole, tenant_role

from file_storage import constants

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def _resolve_file_labels(db: AsyncSession, ids: list[str]) -> dict[str, str]:
    """Name a stored file by its filename — "q3-report.pdf", not a uuid.

    Ids that are not uuids belong to some other id space and are left unnamed,
    which falls back to showing the id as stored.
    """
    import uuid as _uuid

    from sqlalchemy import select

    from file_storage.models import StoredFile

    wanted: dict[_uuid.UUID, str] = {}
    for raw in ids:
        try:
            wanted[_uuid.UUID(raw)] = raw
        except (ValueError, AttributeError, TypeError):
            continue
    if not wanted:
        return {}
    # Deliberately cross-tenant: the audit log is a platform screen listing
    # every tenant's entries, and the entry it labels already records the
    # filename among its captured fields, so naming it discloses nothing new.
    # Scoped to the bound tenant instead, it would fail closed for a platform
    # admin with no organisation and leave every other tenant's file a uuid.
    stmt = select(StoredFile.id, StoredFile.filename).where(StoredFile.id.in_(list(wanted)))
    rows = (await db.execute(stmt.execution_options(all_tenants=True))).all()
    return {wanted.get(file_id, str(file_id)): filename for file_id, filename in rows}


class FileStorageModule(ModuleBase):
    meta = ModuleMeta(
        name=constants.MODULE_PASCAL,
        route_prefix=constants.ROUTE_PREFIX_API,
        view_prefix=constants.ROUTE_PREFIX_VIEW,
        # Needs Settings to run first so register_module_settings can reach
        # app.state.settings.module_registry during register_settings.
        depends_on=[constants._MODULE_SETTINGS],
        i18n_audience="admin",
    )

    def register_settings(self, app: FastAPI) -> None:
        import importlib

        from file_storage.services import FileStorageServices
        from file_storage.settings import FileStorageSettings

        # SM009 is AST-based: a static `from settings.registration import ...`
        # from a module helper is fine (plugin→plugin), but we resolve via
        # importlib here to match the convention used framework-side and to
        # keep the dependency direction one-way explicit.
        register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings

        register_module_settings(
            app,
            "file_storage",
            FileStorageSettings,
            lambda s: FileStorageServices(settings=s),
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from file_storage.endpoints.api import router as api
        from file_storage.endpoints.public import router as public
        from file_storage.endpoints.views import router as views

        api_router.include_router(api)
        api_router.include_router(public)
        view_router.include_router(views)

    def register_public_routes(self, registry: PublicRouteRegistry) -> None:
        """Let anyone GET a file its owner marked public (#353).

        GET-only and anchored to ``/public/{id}[/{name}|/thumbnail]``, so
        uploads, deletes and the authenticated download keep requiring a
        session. The handler itself still refuses anything not ``public``.
        """
        from file_storage.constants import PUBLIC_FILES_RATE
        from file_storage.cookieless import PUBLIC_PATH_PATTERN

        # Its own, wider bucket: one public page can embed dozens of images and
        # thumbnails, which would exhaust the shared anonymous default.
        registry.add_regex(PUBLIC_PATH_PATTERN, methods={"GET"}, rate=PUBLIC_FILES_RATE)

    def register_middleware(self, app: FastAPI) -> None:
        """Serve public files without a session cookie or ``Vary: Cookie``."""
        from file_storage.cookieless import CookielessPublicFilesMiddleware

        app.add_middleware(CookielessPublicFilesMiddleware)

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        """Name file rows in the audit log, and tag them with their table.

        No ``url_template``: a stored file has no page of its own — the browse
        screen is a list, not a record — so the audit cell shows the filename
        unlinked beside a copyable id. Registering anyway is the point: without
        it every upload reads as ``StoredFile`` plus a uuid, and the reader has
        to go and look up which file that was.
        """
        from file_storage.models import StoredFile

        registry.register(
            AuditLink(
                # Class name, not __tablename__ — see AuditLink.entity_type.
                entity_type=StoredFile.__name__,
                url_template="",
                label="File",
                label_key=f"{constants.LOCALE_NAMESPACE}.audit.file",
                table_name=constants.TABLE_STORED_FILE,
                label_resolver=_resolve_file_labels,
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            constants.MODULE_DISPLAY_NAME,
            [
                constants.Permission.UPLOAD,
                constants.Permission.DOWNLOAD,
                constants.Permission.DELETE,
                constants.Permission.MANAGE,
            ],
        )
        read_write = [constants.Permission.UPLOAD, constants.Permission.DOWNLOAD]
        # Deleting is an organisation-admin act (#383). The platform ``user``
        # role used to carry it too, which — every account holds ``user`` —
        # would hand it straight back to each tenant member.
        registry.map_role(constants.USER_ROLE, read_write)
        registry.map_role(tenant_role(TenantRole.MEMBER), read_write)
        for role in (TenantRole.ADMIN, TenantRole.OWNER):
            registry.map_role(tenant_role(role), [*read_write, constants.Permission.DELETE])

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=constants.MODULE_DISPLAY_NAME,
                label_key="file_storage.nav.files",
                url=f"{constants.ROUTE_PREFIX_VIEW}/",
                icon=constants.MENU_ICON,
                order=constants.MENU_ORDER,
                section=MenuSection.SIDEBAR,
                # Platform admins, and every member of the active organisation
                # (the files screen is where a tenant's own uploads live).
                roles=[constants.ADMIN_ROLE, *(tenant_role(r) for r in TenantRole)],
                group="Content",
                group_key="ui.nav_groups.content",
            )
        )

    def register_body_limits(self, registry: BodyLimitRegistry) -> None:
        # The upload is multipart and its own ceiling (``max_file_size_bytes``,
        # a runtime setting, 100 MB by default) is far above the host's global
        # body guard. Track it, plus headroom for the multipart framing.
        registry.add_exact(
            constants.ROUTE_PREFIX_API + constants.PATH_UPLOAD,
            lambda app: (
                app.state.file_storage.settings.max_file_size_bytes
                + constants.MULTIPART_OVERHEAD_BYTES
            ),
            methods={"POST"},
        )

    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        registry.add(
            FeatureFlagDefinition(
                name=constants.FeatureFlag.PUBLIC_UPLOADS,
                description="Allow unauthenticated uploads (future).",
                default_enabled=False,
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {constants.LOCALE_NAMESPACE: base}

    async def on_startup(self, app: FastAPI) -> None:
        """Build the storage backend and probe its backing resource.

        Backend construction is deferred to ``on_startup`` so settings
        hydrated from the DB (between ``register_settings`` and here) are
        picked up — constructing in ``register_settings`` would bake in
        the pydantic defaults instead of the DB overrides.
        """
        from file_storage.aggregates import register_invalidation
        from file_storage.backends import build_backend

        # With multi_tenant off the install is the only tenant, so ordinary
        # users keep deleting their files. With it on every tenant member also
        # holds ``user``, so the grant stays on the organisation-admin roles.
        # Done here because register_permissions cannot see the settings.
        if not getattr(app.state.sm.settings, "multi_tenant", False):
            app.state.sm.permissions.map_role(constants.USER_ROLE, [constants.Permission.DELETE])

        services = app.state.file_storage
        settings = services.settings
        services.backend = build_backend(settings)
        if settings.backend == constants.BackendId.FILESYSTEM:
            root = settings.resolved_fs_root()
            root.mkdir(parents=True, exist_ok=True)
            logger.info("file_storage filesystem backend ready at %s", root)
        elif settings.backend == constants.BackendId.S3:
            logger.info(
                "file_storage S3 backend configured for bucket=%s region=%s endpoint=%s",
                settings.s3_bucket,
                settings.s3_region,
                settings.s3_endpoint_url or "(default)",
            )

        # Wire the browse screen's cached bucket totals to this app's sessions,
        # so any commit that wrote a file row drops them. Registered here rather
        # than in ``register_settings`` because ``app.state.sm.db`` is opened by
        # the lifespan, which has not run at registration time.
        register_invalidation(app.state.sm.db, services.aggregates)

        # Registered here, not in register_health_checks: the backend does not
        # exist until this hook builds it, and the check must follow later
        # settings changes rather than pinning the boot-time instance.
        from simple_module_core.health import HealthCheck

        from file_storage.health import CHECK_BACKEND, build_backend_check

        app.state.sm.health_registry.add(
            HealthCheck(
                name=CHECK_BACKEND,
                check=build_backend_check(app),
                module=self.meta.name,
                # On demand only: an S3 request per readiness probe is billed
                # traffic and ties probe latency to the provider.
                probe=False,
            )
        )
