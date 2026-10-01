"""Per-tenant branding: the request's tenant's overrides over the system theme (#373).

Branding has no table. The system theme is ``app.state.branding.settings``
(SYSTEM-scope settings, hydrated at boot, hot-swapped on save); a tenant's own
values are ``branding.<field>`` rows at settings' TENANT scope, for the fields
in ``TENANT_FIELDS``. :func:`resolve` merges the two for one request.

Cost model:

* ``multi_tenant`` off, or no tenant on the request — returns the system
  object as is. No lookup, no allocation: a single-tenant install renders
  exactly as before.
* a tenant — one read of its override rows per :data:`TENANT_CACHE_TTL_SECONDS`
  per process, cached by tenant id. The merged result is cached alongside and
  rebuilt (without a read) when the system object is swapped.

The cache only ever *forgets* on settings' ``settings.values`` invalidation
notices (a tenant's ``branding.*`` row changed, or a system one — which every
tenant inherits); the TTL is the floor when a notice is lost.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache
from pydantic import ValidationError

from branding.constants import PACKAGE, TENANT_CACHE_TTL_SECONDS, TENANT_FIELDS
from branding.settings import BrandingSettings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from settings.service import SettingService
    from simple_module_core.invalidation import Invalidation, InvalidationBus
    from starlette.requests import Request

logger = logging.getLogger(__name__)

_PREFIX = f"{PACKAGE}."


@dataclass(slots=True)
class TenantCache:
    """One app's tenant-branding cache, held as ``app.state.branding.tenant_cache``.

    Per app, not per process: two apps in one process (tests, embedding) must
    not serve each other's overrides, and an invalidation heard by one must
    not drop the other's.
    """

    # tenant id -> (raw overrides, system object merged against, merged result)
    entries: TTLCache[str, tuple[dict[str, str], BrandingSettings, ResolvedBranding]] = field(
        default_factory=lambda: TTLCache(maxsize=10_000, ttl=TENANT_CACHE_TTL_SECONDS)
    )
    # Bumped by every forget, so a read that started before an invalidation does
    # not store its (possibly stale) result after it.
    epoch: int = 0
    # tenant id -> (epoch the read started in, the read). Single-flight:
    # concurrent misses for one tenant share one read instead of each opening a
    # session.
    inflight: dict[str, tuple[int, asyncio.Future[dict[str, str]]]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolvedBranding:
    """The theme one request sees, and which fields its tenant supplied."""

    settings: BrandingSettings
    tenant_id: str | None = None
    tenant_fields: frozenset[str] = field(default_factory=frozenset)

    def owner_of(self, name: str) -> str | None:
        """The tenant owning ``name``'s value, or ``None`` for the platform's."""
        return self.tenant_id if name in self.tenant_fields else None


def forget(app: FastAPI, tenant_id: str | None = None) -> None:
    """Drop one tenant's entry in ``app``, or every entry when ``tenant_id`` is ``None``."""
    cache: TenantCache = app.state.branding.tenant_cache
    cache.epoch += 1
    # A read already in flight may predate the change: later misses must start
    # a fresh one rather than join it (its own waiters still get their answer).
    if tenant_id is None:
        cache.entries.clear()
        cache.inflight.clear()
    else:
        cache.entries.pop(tenant_id, None)
        cache.inflight.pop(tenant_id, None)


def subscribe(bus: InvalidationBus, app: FastAPI) -> None:
    from settings.constants import INVALIDATION_CHANNEL
    from settings.contracts.invalidation import parse_invalidation_key

    def on_settings_changed(inv: Invalidation) -> None:
        tenant_id, key = parse_invalidation_key(inv.key)
        if key is not None and not key.startswith(_PREFIX):
            return  # someone else's setting
        # A system value is inherited by every tenant without its own override.
        forget(app, tenant_id)

    bus.subscribe(INVALIDATION_CHANNEL, on_settings_changed)


def tenancy_active(app: FastAPI) -> bool:
    settings = getattr(getattr(app.state, "sm", None), "settings", None)
    return bool(getattr(settings, "multi_tenant", False))


def request_tenant(request: Request) -> str | None:
    """The tenant whose branding this request sees; ``None`` means the system's."""
    if not tenancy_active(request.app):
        return None
    return getattr(request.state, "tenant_id", None) or None


async def overrides_from(service: SettingService, tenant_id: str) -> dict[str, str]:
    """The tenant's ``TENANT_FIELDS`` overrides, as seen by ``service``'s session."""
    from settings.contracts.schemas import SettingScope

    rows = await service.list_by_scope_unmasked(SettingScope.TENANT, tenant_id)
    out: dict[str, str] = {}
    for row in rows:
        name = row.key.removeprefix(_PREFIX)
        if row.key.startswith(_PREFIX) and name in TENANT_FIELDS:
            out[name] = row.value
    return out


async def read_overrides(app: FastAPI, tenant_id: str) -> dict[str, str]:
    """:func:`overrides_from` on a short-lived session of its own.

    Only for reads ahead of a request's own work (shared props, the asset
    routes): a request that has already written must use its own session.
    """
    from settings.service import SettingService

    async with app.state.sm.db.session_factory() as db:
        return await overrides_from(SettingService(db), tenant_id)


def merge(system: BrandingSettings, tenant_id: str, overrides: dict[str, str]) -> ResolvedBranding:
    """``system`` with ``overrides`` on top; a value that fails validation is dropped.

    Writes are validated, so a bad value means a hand-edited row — it must
    degrade to the system value for that field, not break every page render.

    An empty-string override is *unset*: the field inherits the platform's
    value. To go back to inheriting, delete the override; storing ``""`` has
    the same effect rather than blanking the platform's value.

    The dark logo is paired with the light one: a tenant that overrides the
    logo but not the dark logo must not be shown the *platform's* dark logo
    beside its own logo, so the inherited dark logo is dropped and dark
    surfaces fall back to the tenant's logo.
    """
    good = {name: value for name, value in overrides.items() if value != ""}
    base: dict[str, Any] = system.model_dump()
    while good:
        try:
            values = {**base, **good}
            if "logo_file_id" in good and "logo_dark_file_id" not in good:
                values["logo_dark_file_id"] = ""
            merged = BrandingSettings(**values)
            return ResolvedBranding(merged, tenant_id, frozenset(good))
        except ValidationError as exc:
            bad = {str(err["loc"][0]) for err in exc.errors() if err.get("loc")}
            logger.warning("Tenant %s branding override(s) %s are invalid.", tenant_id, bad)
            if not bad & good.keys():
                break
            for name in bad:
                good.pop(name, None)
    return ResolvedBranding(system, tenant_id, frozenset())


def _shared_read(
    app: FastAPI, cache: TenantCache, tenant_id: str
) -> tuple[int, asyncio.Future[dict[str, str]]]:
    """The in-flight override read for ``tenant_id``, started if there is none."""
    entry = cache.inflight.get(tenant_id)
    if entry is not None:
        return entry
    read = asyncio.ensure_future(read_overrides(app, tenant_id))
    entry = (cache.epoch, read)
    cache.inflight[tenant_id] = entry

    def _done(_: asyncio.Future[dict[str, str]]) -> None:
        if cache.inflight.get(tenant_id) is entry:
            del cache.inflight[tenant_id]

    read.add_done_callback(_done)
    return entry


async def resolve_for(app: FastAPI, tenant_id: str | None) -> ResolvedBranding:
    system: BrandingSettings = app.state.branding.settings
    if not tenant_id:
        return ResolvedBranding(system)
    cache: TenantCache = app.state.branding.tenant_cache
    hit = cache.entries.get(tenant_id)
    if hit is not None:
        overrides, merged_against, resolved = hit
        if merged_against is system:
            return resolved
    else:
        started, read = _shared_read(app, cache, tenant_id)
        # Shielded: one waiter being cancelled must not cancel everyone's read.
        overrides = await asyncio.shield(read)
        if cache.epoch != started:
            return merge(system, tenant_id, overrides)  # don't cache a racing read
    resolved = merge(system, tenant_id, overrides)
    cache.entries[tenant_id] = (overrides, system, resolved)
    return resolved


async def resolve(request: Request) -> ResolvedBranding:
    """The branding ``request`` sees: its tenant's, falling back to the system's."""
    return await resolve_for(request.app, request_tenant(request))


__all__ = [
    "ResolvedBranding",
    "TenantCache",
    "forget",
    "merge",
    "overrides_from",
    "read_overrides",
    "request_tenant",
    "resolve",
    "resolve_for",
    "subscribe",
    "tenancy_active",
]
