"""Declare branding's tenant-overridable settings keys (#373).

Each field in ``TENANT_FIELDS`` becomes a ``SettingDefinition`` with
``tenant_overridable=True``, so a tenant owner/admin can set it for their own
tenant through settings' ``/api/settings/tenant/current/{key}`` and see it on
the organisation settings page. Every TENANT-scope write — self-service or a
platform operator writing on a tenant's behalf — runs :func:`_check` first:

* a scalar must pass the same validator the system value does (422);
* a design pack must be one an installed module provides (422);
* an image key is refused on every generic settings write *and delete* route
  (422, ``clear_via``): images are set and cleared only through
  ``/api/branding/tenant/{asset}``, which validates the bytes as an image,
  stores them as the tenant's own file and reaps the file it replaces or
  clears once the write commits. A generic write could do none of that — it
  could point the logo at any file the tenant owns (a PDF), and a generic
  delete would leave the file behind. (A row left by a deleted tenant is the
  one thing a platform operator may still delete by hand.)

An empty override is the same as none: the tenant inherits the platform's
value. To go back to inheriting, delete the override.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from branding.constants import (
    IMAGE_KEY_GENERIC_WRITE_ERROR,
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
    "primary_color": "Accent colour as #rrggbb. Delete the override to use the platform's.",
    "design_pack": "Design pack slug. Delete the override to use the platform's.",
    "footer_text": "Footer caption. Delete the override to show the platform's.",
    "logo_file_id": "Logo image.",
    "logo_dark_file_id": "Logo for dark surfaces; falls back to the tenant's own logo.",
    "favicon_file_id": "Browser tab icon.",
}
_ASSET_OF = {field: asset for asset, field in TENANT_ASSETS.items()}


def _make_check(name: str):
    async def check(request: Request, tenant_id: str, value: str) -> None:
        if name in TENANT_IMAGE_FIELDS:
            raise ValueError(IMAGE_KEY_GENERIC_WRITE_ERROR.format(asset=_ASSET_OF[name]))
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
        upload_url = f"{ROUTE_PREFIX}/tenant/{asset}" if asset else ""
        registry.add(
            SettingDefinition(
                key=f"{PACKAGE}.{name}",
                default=str(defaults[name]),
                description=_DESCRIPTIONS[name],
                description_key=f"{PACKAGE}.tenant_settings.{name}",
                tenant_overridable=True,
                check=_make_check(name),
                upload_url=upload_url,
                clear_via=upload_url,
            )
        )


__all__ = ["register_tenant_definitions"]
