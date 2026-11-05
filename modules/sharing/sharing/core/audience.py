"""Which user ids a request may act on or name: the active tenant's members.

On a multi-tenant app a grantee, and any user label shown, must belong to the
active tenant; otherwise ``sharing`` would let a caller share with (and probe
for) accounts in other tenants and read their directory labels. Membership is
asked through ``simple_module_core.tenancy.tenant_member_ids`` (the
``tenants`` module publishes it), so this module never imports ``tenants``.
With no active tenant, or no membership store installed, nobody is in the
audience (fail closed). A single-tenant app has no such boundary.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from simple_module_core.tenancy import TenancyMode, tenant_member_ids
from simple_module_db.tenancy import current_tenant_id
from simple_module_hosting.tenancy import tenancy_mode


class Audience:
    """Filters user ids down to those the current request may see."""

    def __init__(self, app: Any, db: Any) -> None:
        self.app = app
        self.db = db

    async def visible(self, user_ids: Collection[str]) -> set[str]:
        wanted = {uid for uid in user_ids if uid}
        if not wanted or tenancy_mode(self.app) is not TenancyMode.MULTI:
            return wanted
        tenant_id = current_tenant_id.get()
        if tenant_id is None:
            return set()
        members = await tenant_member_ids(self.app, self.db, tenant_id, wanted)
        return members or set()


class OpenAudience:
    """Everyone is visible (single-tenant use, or tests without an app)."""

    async def visible(self, user_ids: Collection[str]) -> set[str]:
        return {uid for uid in user_ids if uid}
