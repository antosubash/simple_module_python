"""Tenants module settings (DB-backed, edited on the Settings screen)."""

from __future__ import annotations

from pydantic import Field
from simple_module_core.settings_base import DbBackedSettings


class TenantsSettings(DbBackedSettings):
    """Configuration for the tenants module."""

    allow_self_service: bool = Field(
        default=True,
        description="Let any signed-in user create an organisation. Off: platform admins only.",
    )
    public_base_url: str = Field(
        default="",
        description=(
            "Origin invitation links are built on, e.g. https://app.example.com. "
            "Empty: links are root-relative and never taken from the request's Host header."
        ),
    )
    subdomain_base: str = Field(
        default="",
        description=(
            "Resolve the tenant from the host: with 'example.com', acme.example.com "
            "is the tenant whose slug is 'acme' — also for anonymous visitors on "
            "public routes. Empty: off."
        ),
    )
    invitation_ttl_hours: int = Field(
        default=72, ge=1, le=24 * 30, description="How long an invitation link stays valid."
    )
