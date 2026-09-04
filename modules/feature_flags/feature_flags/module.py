"""FeatureFlags module definition."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from feature_flags.constants import (
    AUDIT_LINK_LABEL,
    AUDIT_LINK_LABEL_KEY,
    LOCALE_NAMESPACE,
    MENU_ICON,
    MENU_LABEL,
    MENU_ORDER,
    MENU_URL,
    PERM_FEATURE_FLAGS_MANAGE,
    PERM_FEATURE_FLAGS_VIEW,
    PERM_GROUP,
    QP_OVERRIDE,
    VIEW_PREFIX,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)


async def _resolve_override_labels(db: AsyncSession, ids: list[str]) -> dict[str, str]:
    """Name an override row by the flag it overrides.

    The row's primary key is an autoincrementing integer with no meaning
    outside the table. What a reader of "someone changed override 12" wants to
    know is *which flag* — so the label is the flag name, not the id, and not
    the row's scope (which the flags screen shows once the link is followed).
    """
    from sqlalchemy import select

    from feature_flags.models import FeatureFlagOverride

    numeric = {int(raw): raw for raw in ids if raw.lstrip("-").isdigit()}
    if not numeric:
        return {}
    rows = (
        await db.execute(
            select(FeatureFlagOverride.id, FeatureFlagOverride.name).where(
                FeatureFlagOverride.id.in_(list(numeric))
            )
        )
    ).all()
    return {numeric.get(row_id, str(row_id)): name for row_id, name in rows}


class FeatureFlagsModule(ModuleBase):
    meta = ModuleMeta(
        name="FeatureFlags",
        route_prefix="/api/feature_flags",
        view_prefix=VIEW_PREFIX,
        i18n_audience="admin",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from feature_flags.endpoints.api import router as api
        from feature_flags.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                label_key="feature_flags.nav.feature_flags",
                url=MENU_URL,
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.ADMIN_SIDEBAR,
                group="System",
                group_key="ui.nav_groups.system",
                # Mirrors the view router's guard. Without it the entry shows
                # for every signed-in account and 403s on click.
                permissions=[PERM_FEATURE_FLAGS_VIEW],
            )
        )

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        """Point audit rows for an override back at the flags screen.

        The browse footer promises every toggle is written to the audit log;
        the reverse trip is what makes that promise useful. There is no
        per-override page, so the link lands on the table with the row's id in
        the query string rather than inventing a detail screen for a two-column
        record.
        """
        from feature_flags.models import FeatureFlagOverride

        registry.register(
            AuditLink(
                # Class name, not __tablename__ — see AuditLink.entity_type.
                # The table name travels alongside as the audit log's type tag.
                entity_type=FeatureFlagOverride.__name__,
                url_template=f"{MENU_URL}?{QP_OVERRIDE}={{id}}",
                label=AUDIT_LINK_LABEL,
                label_key=AUDIT_LINK_LABEL_KEY,
                table_name=FeatureFlagOverride.__tablename__,
                label_resolver=_resolve_override_labels,
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            PERM_GROUP,
            [
                PERM_FEATURE_FLAGS_VIEW,
                PERM_FEATURE_FLAGS_MANAGE,
            ],
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {LOCALE_NAMESPACE: base}

    async def on_startup(self, app: FastAPI) -> None:
        """Load every persisted override into the in-memory registry.

        Called once, after DB init and before the app starts serving. From
        here on ``registry.is_enabled`` reflects admin overrides even for
        requests that don't hit this module's endpoints.

        If the DB read fails (store unreachable, table missing, etc.) we
        log a warning and continue with the registry at its
        ``register_feature_flags``-declared defaults rather than letting a
        transient outage take the whole app down. Defaults are the
        conservative choice — admins can re-toggle overrides once the
        store is healthy again.
        """
        from feature_flags.service import FeatureFlagService

        sm = app.state.sm
        try:
            async with sm.db.session_factory() as session:
                service = FeatureFlagService(session)
                await service.hydrate_registry(sm.feature_flags)
        except Exception:
            _logger.exception("feature_flags.hydrate_failed — continuing with registry defaults")
