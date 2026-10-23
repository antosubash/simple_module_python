"""Bound public-file tenant lookups; deletion events accelerate TTL eviction."""

from collections import OrderedDict
from time import monotonic

from fastapi import FastAPI
from simple_module_core.events import EventBus
from simple_module_core.tenancy import tenant_exists
from simple_module_core.tenant_events import TenantDeleted

TENANT_EXISTS_TTL_SECONDS = 60
TENANT_EXISTS_CACHE_SIZE = 1024


class TenantExistenceCache:
    def __init__(self) -> None:
        self.entries: OrderedDict[str, tuple[float, bool | None]] = OrderedDict()
        self.generation = 0

    def forget(self, tenant_id: str) -> None:
        self.generation += 1
        self.entries.pop(tenant_id, None)


async def cached_tenant_exists(app: FastAPI, tenant_id: str) -> bool | None:
    cache = getattr(app.state, "file_storage_tenant_cache", None)
    if cache is None:
        cache = app.state.file_storage_tenant_cache = TenantExistenceCache()
    now = monotonic()
    entry = cache.entries.get(tenant_id)
    if entry is not None and now - entry[0] < TENANT_EXISTS_TTL_SECONDS:
        return entry[1]
    generation = cache.generation
    answer = await tenant_exists(app, tenant_id)
    # An in-flight lookup must not restore an entry evicted by deletion.
    if generation == cache.generation:
        cache.entries[tenant_id] = (now, answer)
        cache.entries.move_to_end(tenant_id)
        while len(cache.entries) > TENANT_EXISTS_CACHE_SIZE:
            cache.entries.popitem(last=False)
    return answer


def register_tenant_cache(bus: EventBus, app: FastAPI) -> None:
    app.state.file_storage_tenant_cache = TenantExistenceCache()

    async def forget(event: TenantDeleted) -> None:
        app.state.file_storage_tenant_cache.forget(event.tenant_id)

    bus.subscribe(TenantDeleted, forget)
