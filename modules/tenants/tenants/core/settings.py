"""Tenants module settings (DB-backed, edited on the Settings screen)."""

from __future__ import annotations

import re

from pydantic import Field, field_validator
from simple_module_core.settings.settings_base import DbBackedSettings


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
            "Empty: inherit host.public_base_url; if both are blank, links are root-relative."
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

    @field_validator("subdomain_base")
    @classmethod
    def _check_subdomain_base(cls, value: str) -> str:
        value = value.strip().lower()
        if value and (
            len(value) > 253
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in value.removesuffix(".").split(".")
            )
        ):
            raise ValueError(
                "subdomain_base must be a hostname of at most 253 characters "
                "without a scheme, path or port (e.g. example.com), or blank"
            )
        return value

    invitation_ttl_hours: int = Field(
        default=72,
        ge=1,
        le=24 * 30,
        description=(
            "How long an invitation link stays valid (1-720 hours). "
            "Gültigkeitsdauer eines Einladungslinks (1-720 Stunden)."
        ),
    )
