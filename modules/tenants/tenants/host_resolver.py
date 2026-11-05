"""Subdomain tenant resolution (#363): ``acme.example.com`` -> tenant ``acme``.

The one source that works for anonymous visitors, so a public site (pagebuilder,
a records viewer) can serve the right tenant without a sign-in. Enabled by the
``subdomain_base`` setting (e.g. ``example.com``); empty disables it.

Binding rules, by who is asking:

* **member** of the subdomain's tenant — bound with their membership role,
  exactly as if they had switched to it;
* **anonymous** — bound; ``AuthMiddleware`` already limits them to public
  routes, so they see only what the tenant publishes;
* **signed-in non-member** — bound on public routes only. On an authenticated
  route a platform-wide permission (a ``user`` role mapped to ``x.view``)
  would otherwise read a tenant the user does not belong to.

An unknown or suspended subdomain binds nothing and never falls back to the
session's tenant: the host named a tenant, and it is not that one.
"""

from __future__ import annotations

from cachetools import TTLCache
from fastapi import FastAPI
from simple_module_core.app_state import get_public_routes
from simple_module_core.singleflight import MAX_FILL_ATTEMPTS
from sqlalchemy import select
from starlette.requests import Request

from tenants.constants import TenantStatus
from tenants.models import Tenant

HOST_TTL_SECONDS = 60
NEGATIVE_HOST_TTL_SECONDS = 5
# Membership keys are user ids; this prefix marks a key that names one slug.
HOST_KEY_PREFIX = "host:"
_MISSING_SLUGS: TTLCache[str, bool] = TTLCache(maxsize=10_000, ttl=NEGATIVE_HOST_TTL_SECONDS)
_BY_SLUG: TTLCache[str, tuple[str, str]] = TTLCache(maxsize=10_000, ttl=HOST_TTL_SECONDS)
# Bumped on every forget: a lookup that started earlier must not cache its stale row.
_epoch = 0


def host_invalidation_key(slug: str) -> str:
    """Invalidation key that drops one slug's host lookups (see ``resolver.forget``)."""
    return f"{HOST_KEY_PREFIX}{slug}"


def forget_hosts() -> None:
    global _epoch
    _epoch += 1
    _BY_SLUG.clear()
    _MISSING_SLUGS.clear()


def forget_slug(slug: str) -> None:
    global _epoch
    _epoch += 1
    _BY_SLUG.pop(slug, None)
    _MISSING_SLUGS.pop(slug, None)


def subdomains_enabled(request: Request) -> bool:
    return bool(request.app.state.tenants.settings.subdomain_base.strip().strip("."))


def subdomain_slug(request: Request) -> str | None:
    """The tenant slug named by the request's host, if subdomains are enabled."""
    base = request.app.state.tenants.settings.subdomain_base.strip().lower().strip(".")
    host = (request.url.hostname or "").lower()
    if not base or not host.endswith("." + base):
        return None
    slug = host[: -len(base) - 1]
    return slug if slug and "." not in slug else None


async def tenant_for_slug(app: FastAPI, slug: str) -> tuple[str, str] | None:
    """``(tenant_id, status)`` for a slug, cached briefly."""
    row = None
    for _ in range(MAX_FILL_ATTEMPTS):
        hit = _BY_SLUG.get(slug)
        if hit is not None:
            return hit
        if _MISSING_SLUGS.get(slug):
            return None
        started = _epoch
        row = await _read_slug(app, slug)
        if started == _epoch:
            if row is None:
                _MISSING_SLUGS[slug] = True
            else:
                _BY_SLUG[slug] = row
            return row
    # Invalidated during every read: the last read started after the last
    # invalidation this request saw, so answer with it but cache nothing.
    return row


async def _read_slug(app: FastAPI, slug: str) -> tuple[str, str] | None:
    async with app.state.sm.db.session_factory() as db:
        row = (
            await db.execute(select(Tenant.id, Tenant.status).where(Tenant.slug == slug))
        ).first()
    return None if row is None else (row[0], row[1])


def is_public_route(request: Request) -> bool:
    registry = get_public_routes(request.app)
    return registry is not None and registry.matches(request.method, request.url.path)


async def resolve_from_host(request: Request, slug: str) -> tuple[str | None, bool]:
    """``(tenant_id, active)`` for the subdomain; ``(None, False)`` if unusable."""
    found = await tenant_for_slug(request.app, slug)
    if found is None or found[1] != TenantStatus.ACTIVE:
        if found is not None:
            request.state.tenant_suspended = True
        return None, False
    return found[0], True


__all__ = [
    "HOST_KEY_PREFIX",
    "forget_hosts",
    "forget_slug",
    "host_invalidation_key",
    "is_public_route",
    "resolve_from_host",
    "subdomain_slug",
    "tenant_for_slug",
]
