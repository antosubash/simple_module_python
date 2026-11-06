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

from typing import Literal

from cachetools import TTLCache
from fastapi import FastAPI
from simple_module_core.app_state import get_public_routes, get_services
from simple_module_core.invalidation import Invalidation, InvalidationBus
from simple_module_core.singleflight import MISS, Miss, fill
from sqlalchemy import select
from starlette.requests import Request

from tenants.core.constants import HOSTS_INVALIDATION_CHANNEL, TenantStatus
from tenants.models import Tenant

HOST_TTL_SECONDS = 60
NEGATIVE_HOST_TTL_SECONDS = 5
_MISSING_SLUGS: TTLCache[str, bool] = TTLCache(maxsize=10_000, ttl=NEGATIVE_HOST_TTL_SECONDS)
_BY_SLUG: TTLCache[str, tuple[str, str]] = TTLCache(maxsize=10_000, ttl=HOST_TTL_SECONDS)
# Bumped on every forget: a lookup that started earlier must not cache its stale row.
_epoch = 0


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


def forget_host(slug: str | None) -> None:
    """Drop one slug's lookups, or every slug's on ``None``."""
    if slug is None:
        forget_hosts()
    else:
        forget_slug(slug)


def _apply_invalidation(inv: Invalidation) -> None:
    forget_host(inv.key)


def subscribe_hosts(bus: InvalidationBus) -> None:
    """Drop host lookups on ``HOSTS_INVALIDATION_CHANNEL`` (key: a slug, or ``None``)."""
    bus.subscribe(HOSTS_INVALIDATION_CHANNEL, _apply_invalidation)


def make_host_invalidator(app: FastAPI):
    """``TenantService(invalidate_hosts=...)``: forget here now, then tell the other workers."""

    async def invalidate(slug: str | None) -> None:
        forget_host(slug)
        bus = getattr(get_services(app), "invalidation", None)
        if bus is not None:
            await bus.publish(HOSTS_INVALIDATION_CHANNEL, key=slug)

    return invalidate


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
    """``(tenant_id, status)`` for a slug, cached briefly (unknown slugs too)."""

    def cached() -> tuple[str, str] | Literal[Miss.MISS] | None:
        hit = _BY_SLUG.get(slug)
        if hit is not None:
            return hit
        return None if _MISSING_SLUGS.get(slug) else MISS

    def store(row: tuple[str, str] | None) -> None:
        if row is None:
            _MISSING_SLUGS[slug] = True
        else:
            _BY_SLUG[slug] = row

    return await fill(
        lambda: _read_slug(app, slug), epoch=lambda: _epoch, store=store, cached=cached
    )


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
    "forget_host",
    "forget_hosts",
    "forget_slug",
    "is_public_route",
    "make_host_invalidator",
    "resolve_from_host",
    "subdomain_slug",
    "subscribe_hosts",
    "tenant_for_slug",
]
