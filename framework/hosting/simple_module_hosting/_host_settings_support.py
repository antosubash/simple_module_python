"""Restart-required markers and validator bodies for :class:`HostSettings`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_core import PydanticCustomError
from simple_module_core.cors import WILDCARD as CORS_WILDCARD
from simple_module_core.discovery import DEFAULT_AUTH_PROVIDER
from simple_module_core.stored_settings import RELATED_FIELDS_CTX

if TYPE_CHECKING:
    from simple_module_hosting.host_settings import HostSettings

# Marks a field the running process cannot pick up without a restart, so the
# admin UI can say so rather than letting the edit look like it took effect.
_RESTART_DB = {"requires_restart": True, "group": "Database"}
_RESTART_GUARD = {"requires_restart": True, "group": "Request guards"}
_RESTART_CORS = {"requires_restart": True, "group": "CORS"}
_RESTART_API = {"requires_restart": True, "group": "API"}

# Consumed while create_app builds the tenant middleware, the strict tenant
# filter, the i18n registry and LocaleMiddleware, the auth provider and the
# public-route registry, the proxy middleware and logging — none of which the
# lifespan hydration can rebuild (#499). test_build_time_settings_marked keeps
# this in step with what create_app actually reads.
_RESTART_TENANCY = {"requires_restart": True, "group": "Tenancy"}
_RESTART_I18N = {"requires_restart": True, "group": "Localization"}
_RESTART_AUTH = {"requires_restart": True, "group": "Authentication"}
_RESTART_LOGGING = {"requires_restart": True, "group": "Logging"}
_RESTART_SECURITY = {"requires_restart": True, "group": "Security"}


def check_public_base_url(value: str) -> str:
    from urllib.parse import urlsplit

    value = value.strip().rstrip("/")
    parts = urlsplit(value)
    if value and not (parts.scheme in ("http", "https") and parts.netloc):
        raise ValueError("public_base_url must be an http(s) origin such as https://example.org")
    return value


def check_rate(value: str) -> str:
    from simple_module_core.rate_limit import parse_rate

    parse_rate(value)  # raises RateLimitError (a ValueError) on a typo
    return value.strip()


def check_native_prefixes(value: list[str]) -> list[str]:
    cleaned = [prefix.strip() for prefix in value]
    for prefix in cleaned:
        if not prefix.startswith("/"):
            raise ValueError(f"native_link_prefixes entry {prefix!r} must start with '/'")
    return cleaned


def check_body_bytes(value: int) -> int:
    if value < 0:
        raise ValueError("max_request_body_bytes must be >= 0 (0 disables the guard)")
    return value


def normalize_auth_provider(value: str) -> str:
    return value.strip() or DEFAULT_AUTH_PROVIDER


def normalize_trusted_proxy(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def check_default_tenant(value: str) -> str:
    from simple_module_db import PLATFORM_TENANT_ID, is_valid_tenant_id

    value = value.strip()
    if value == PLATFORM_TENANT_ID:
        raise ValueError(f"default_tenant {value!r} is reserved for platform-owned rows")
    if value and not is_valid_tenant_id(value):
        raise ValueError(f"default_tenant {value!r} is not a valid tenant id")
    return value


def check_cors_wildcard(settings: HostSettings) -> None:
    if settings.cors_allow_credentials and CORS_WILDCARD in settings.cors_allow_origins:
        raise PydanticCustomError(
            "cors_wildcard_credentials",
            "cors_allow_origins '*' cannot be combined with cors_allow_credentials",
            {RELATED_FIELDS_CTX: ["cors_allow_origins", "cors_allow_credentials"]},
        )


def check_default_locale_supported(settings: HostSettings) -> None:
    if settings.i18n_default_locale not in settings.i18n_supported_locales:
        # Model-level, so the error has no field location: the context
        # names both halves, letting lenient boot hydration drop whichever
        # one came from the DB instead of refusing to boot (#497).
        raise PydanticCustomError(
            "default_locale_unsupported",
            "i18n_default_locale '{default}' is not in i18n_supported_locales {supported}",
            {
                "default": settings.i18n_default_locale,
                "supported": settings.i18n_supported_locales,
                RELATED_FIELDS_CTX: ["i18n_default_locale", "i18n_supported_locales"],
            },
        )
