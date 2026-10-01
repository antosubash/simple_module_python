"""Tenant resolution: which tenant does this request act for?

Registered as ``app.state.tenant_resolver`` and called by the framework's
``TenantMiddleware``. The session only stores a *preference*
(``SESSION_ACTIVE_TENANT``); every request re-validates it against the user's
memberships, so removing a member or suspending a tenant takes effect on the
next request after the cache entry drops (immediately in-process, via
``InvalidationBus`` across workers, ``MEMBERSHIP_TTL_SECONDS`` at worst).

The principal gains ``tenant:<role>`` for the active tenant only; that is how
membership roles reach the permission registry without ever touching the
platform-wide roles.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from cachetools import TTLCache
from fastapi import FastAPI
from simple_module_core.invalidation import Invalidation, InvalidationBus
from simple_module_db import is_valid_tenant_id
from simple_module_hosting.middleware import TenantResolution
from starlette.requests import Request

from tenants.constants import (
    INVALIDATION_CHANNEL,
    SESSION_ACTIVE_TENANT,
    TENANT_ROLE_PREFIX,
    TenantStatus,
)
from tenants.contracts.schemas import MyTenantView
from tenants.host_resolver import (
    forget_hosts,
    is_public_route,
    resolve_from_host,
    subdomain_slug,
    subdomains_enabled,
)
from tenants.service import TenantService

logger = logging.getLogger(__name__)

MEMBERSHIP_TTL_SECONDS = 60

_MEMBERSHIPS: TTLCache[str, list[MyTenantView]] = TTLCache(
    maxsize=10_000, ttl=MEMBERSHIP_TTL_SECONDS
)


# Bumped by every invalidation. A read that started before an invalidation
# must not store its (possibly stale) result afterwards: otherwise a member
# removed while their own request was mid-read is re-cached as a member for a
# whole TTL.
_epoch = 0


def forget(key: str | None) -> None:
    global _epoch
    _epoch += 1
    if key is None:
        _MEMBERSHIPS.clear()
        forget_hosts()  # a status change: cached subdomain lookups are stale too
    else:
        _MEMBERSHIPS.pop(key, None)


def _apply_invalidation(inv: Invalidation) -> None:
    forget(inv.key)


def subscribe(bus: InvalidationBus) -> None:
    bus.subscribe(INVALIDATION_CHANNEL, _apply_invalidation)


def make_invalidator(app: FastAPI):
    async def invalidate(key: str | None) -> None:
        forget(key)  # this worker, now — the bus reaches the others
        bus = getattr(getattr(app.state, "sm", None), "invalidation", None)
        if bus is not None:
            await bus.publish(INVALIDATION_CHANNEL, key=key)

    return invalidate


def cached_memberships(user_id: str) -> list[MyTenantView] | None:
    return _MEMBERSHIPS.get(user_id)


async def memberships_for(app: FastAPI, user_id: str) -> list[MyTenantView]:
    cached = _MEMBERSHIPS.get(user_id)
    if cached is not None:
        return cached
    started = _epoch
    async with app.state.sm.db.session_factory() as db:
        rows = await TenantService(db).list_for_user(user_id)
    views = [
        MyTenantView(
            id=t.id, slug=t.slug, name=t.name, status=t.status, created_at=t.created_at, role=role
        )
        for t, role in rows
    ]
    if _epoch == started:
        _MEMBERSHIPS[user_id] = views
    return views


def pick_active(memberships: list[MyTenantView], preferred: str | None) -> MyTenantView | None:
    """The preferred tenant if it is an active membership, else the first active one."""
    usable = [m for m in memberships if m.status == TenantStatus.ACTIVE]
    for m in usable:
        if m.id == preferred:
            return m
    return usable[0] if usable else None


def _with_tenant_role(user: Any, tenant_id: str, role: str) -> Any:
    if not dataclasses.is_dataclass(user) or isinstance(user, type):
        return user
    roles = [r for r in getattr(user, "roles", []) if not r.startswith(TENANT_ROLE_PREFIX)]
    changes: dict[str, Any] = {"roles": [*roles, f"{TENANT_ROLE_PREFIX}{role}"]}
    if "tenant_id" in {f.name for f in dataclasses.fields(user)}:
        changes["tenant_id"] = tenant_id
    return dataclasses.replace(user, **changes)


async def resolve_tenant(request: Request) -> TenantResolution:
    """``TenantResolver`` for the framework's ``TenantMiddleware``.

    Reports the source (``subdomain`` / ``header`` / ``session``) and the headers
    the answer depended on, so the middleware can set ``Vary``.
    """
    tenant_id, source, vary = await _resolve(request)
    return TenantResolution(tenant_id, source if tenant_id is not None else None, vary)


async def _resolve(request: Request) -> tuple[str | None, str | None, tuple[str, ...]]:
    request.state.tenant_role = None
    request.state.tenant_suspended = False
    request.state.suspended_tenant_name = None
    user = getattr(request.state, "user", None)
    slug = subdomain_slug(request)
    if slug is not None:
        return await _resolve_subdomain(request, user, slug), "subdomain", ("Host",)
    # No slug in the host is still an answer that depended on the host.
    vary: tuple[str, ...] = ("Host",) if subdomains_enabled(request) else ()
    if user is None:
        return None, None, vary
    user_id = str(user.id)
    memberships = await memberships_for(request.app, user_id)

    header_name = _header_name(request)
    if header_name:
        vary = (*vary, header_name)
    requested = request.headers.get(header_name) if header_name else None
    if requested is not None:
        # An explicit per-request choice (API clients). Never fall back to
        # another tenant: a client that asked for X — or sent junk — must not
        # act on Y.
        if not is_valid_tenant_id(requested):
            return None, None, vary
        active = next(
            (m for m in memberships if m.id == requested and m.status == TenantStatus.ACTIVE),
            None,
        )
        if active is None:
            return None, None, vary
        return _enter(request, user, active), "header", vary

    session = request.scope.get("session")
    preferred = session.get(SESSION_ACTIVE_TENANT) if session is not None else None
    active = pick_active(memberships, preferred)
    chosen = next((m for m in memberships if m.id == preferred), None)
    chosen_suspended = chosen is not None and chosen.status == TenantStatus.SUSPENDED
    if chosen_suspended:
        # Falling back to another membership must not be silent: say which
        # organisation was suspended, and keep the choice in the session so
        # the notice stays until the user switches deliberately.
        request.state.tenant_suspended = True
        request.state.suspended_tenant_name = chosen.name

    if active is None:
        request.state.tenant_suspended = any(
            m.status == TenantStatus.SUSPENDED for m in memberships
        )
        return None, None, vary
    if session is not None and preferred != active.id and not chosen_suspended:
        session[SESSION_ACTIVE_TENANT] = active.id
    return _enter(request, user, active), "session", vary


async def _resolve_subdomain(request: Request, user: Any, slug: str) -> str | None:
    tenant_id, active = await resolve_from_host(request, slug)
    if not active or tenant_id is None:
        return None
    if user is not None:
        memberships = await memberships_for(request.app, str(user.id))
        own = next((m for m in memberships if m.id == tenant_id), None)
        if own is not None:
            return _enter(request, user, own)
        if not is_public_route(request):
            return None
    return tenant_id


def _header_name(request: Request) -> str:
    settings = getattr(getattr(request.app.state, "sm", None), "settings", None)
    return getattr(settings, "tenant_header", "") or ""


def _enter(request: Request, user: Any, active: MyTenantView) -> str:
    request.state.tenant_role = active.role
    request.state.user = _with_tenant_role(user, active.id, active.role)
    return active.id


def switch_active(request: Request, tenant_id: str) -> None:
    """Record the user's choice; ``resolve_tenant`` validates it next request."""
    request.session[SESSION_ACTIVE_TENANT] = tenant_id


__all__ = [
    "MEMBERSHIP_TTL_SECONDS",
    "cached_memberships",
    "forget",
    "make_invalidator",
    "memberships_for",
    "pick_active",
    "resolve_tenant",
    "subscribe",
    "switch_active",
]
