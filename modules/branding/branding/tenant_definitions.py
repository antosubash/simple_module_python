"""Declare branding's tenant-overridable settings keys (#373).

Each field in ``TENANT_FIELDS`` becomes a ``SettingDefinition`` with
``tenant_overridable=True``, so a tenant owner/admin can set it for their own
tenant through settings' ``/api/settings/tenant/current/{key}`` and see it on
the organisation settings page. Every TENANT-scope write — self-service or a
platform operator writing on a tenant's behalf — runs :func:`_check` first:

* a scalar must pass the same validator the system value does (422);
* a design pack must be one an installed module provides (422);
* an image id must name a live file **owned by the tenant being written**
  (404 otherwise) — a tenant cannot point its logo at another tenant's upload,
  nor at a platform file.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pydantic import ValidationError
from simple_module_db import all_tenants
from sqlalchemy import select

from branding.constants import (
    PACKAGE,
    ROUTE_PREFIX,
    TENANT_ASSETS,
    TENANT_FIELDS,
    TENANT_IMAGE_FIELDS,
)
from branding.settings import BrandingSettings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request

_DESCRIPTIONS = {
    "app_name": "Application name shown in the header, page titles and emails.",
    "primary_color": "Accent colour as #rrggbb; empty uses the theme default.",
    "design_pack": "Design pack slug; empty uses the base look.",
    "footer_text": "Footer caption; empty shows the platform's.",
    "logo_file_id": "Logo image.",
    "logo_dark_file_id": "Logo for dark surfaces; falls back to the logo.",
    "favicon_file_id": "Browser tab icon.",
}
_ASSET_OF = {field: asset for asset, field in TENANT_ASSETS.items()}


async def tenant_owns_file(app: FastAPI, tenant_id: str, raw: str) -> bool:
    """Whether ``raw`` is the id of a live (not deleted) file owned by ``tenant_id``."""
    from file_storage.models import StoredFile

    try:
        file_id = uuid.UUID(raw)
    except ValueError:
        return False
    stmt = select(StoredFile.id).where(StoredFile.id == file_id, StoredFile.tenant_id == tenant_id)
    # An explicit owner condition, so the answer does not depend on which
    # tenant (if any) the caller happens to be bound to.
    with all_tenants():
        async with app.state.sm.db.session_factory() as db:
            return (await db.execute(stmt)).first() is not None


def _make_check(name: str):
    async def check(request: Request, tenant_id: str, value: str) -> None:
        if name in TENANT_IMAGE_FIELDS:
            if value and not await tenant_owns_file(request.app, tenant_id, value):
                raise LookupError("No such image in this organisation.")
            return
        try:
            BrandingSettings(**{name: value})
        except ValidationError as exc:
            raise ValueError(exc.errors()[0]["msg"]) from exc
        if name == "design_pack" and value:
            registry = getattr(request.app.state, "design_packs", None)
            if registry is None or not registry.has(value):
                raise ValueError(f"Unknown design pack {value!r}.")

    return check


def register_tenant_definitions(app: FastAPI) -> None:
    from settings.contracts.registry import SettingDefinition

    registry = app.state.settings.registry
    defaults = BrandingSettings().model_dump()
    for name in TENANT_FIELDS:
        asset = _ASSET_OF.get(name)
        registry.add(
            SettingDefinition(
                key=f"{PACKAGE}.{name}",
                default=str(defaults[name]),
                description=_DESCRIPTIONS[name],
                tenant_overridable=True,
                check=_make_check(name),
                upload_url=f"{ROUTE_PREFIX}/tenant/{asset}" if asset else "",
            )
        )


__all__ = ["register_tenant_definitions", "tenant_owns_file"]
