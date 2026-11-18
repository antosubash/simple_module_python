# Cache invalidation

`InvalidationBus` tells the *other* worker processes that something they have cached stopped being true. It is in-process by default and cross-process when a transport is installed.

It is not `EventBus` and not a queue. `EventBus` carries domain events inside one process and its handlers may do anything; this carries "forget an entry" and its handlers may only forget. Neither persists, retries, or guarantees delivery — so **every consumer keeps a TTL as its floor** and treats the bus as an accelerator over it. Work that must happen exactly once belongs in a Celery task.

## The problem it solves

Several modules cache a row that is cheap to read and expensive to read *often*:

| Cache | Read on | Expires after | Owner |
|---|---|---|---|
| `User.session_version` | nearly every authenticated request | 30s | `users.accounts.session_version_cache` |
| aggregate storage size | the files index | 30s | `file_storage` |
| hydrated settings objects | every request that reads a setting | 30s periodic reload | `settings` |
| role permission overlays | every permission check | 30s periodic reload | `permissions` |
| feature flag overrides | every flag check | 30s periodic reload | `feature_flags` |

The first two share one failure shape: the worker that performed the write dropped its own entry immediately and **every other worker kept serving the stale value until its own entry expired**. Acceptable for "sign out everywhere"; much less so for a password change made because an account is believed compromised ([#318](https://github.com/antosubash/simple_module_python/issues/318)).

Role overlays, module settings and feature-flag overrides now reload from the committed DB on invalidation (#621). The writing worker publishes only from `db.on_commit`; rollback changes no live state. Reloads replace snapshots so deleted overrides disappear too. Settings reloads emit a local `SettingsReloaded` event when values change. A serialized periodic reload every 30 seconds provides the fallback when a message is lost or broadcasting is disabled; failed reads keep the last snapshot and retry on the next interval.

The obvious fix — publish on Redis pub/sub — was not reachable from any of those modules. Redis belongs to the `background_tasks` plugin, so `users` would have to open a second connection with its own settings that can disagree with it; `SM009` makes a `framework/*` → plugin import an error, so the framework cannot borrow the plugin's client either. Hence the split below.

## Who owns what

| Layer | Owns | Knows about |
|---|---|---|
| `users`, and any other cache-owning module | which channels exist, and what "forget" means for its own cache | the bus |
| `InvalidationBus` (`framework/core`) | the channel registry, the wire format, the origin filter | nothing below it |
| `RedisInvalidationTransport` (`background_tasks`) | the connection, the subscription, reconnection | the bus and Redis |

Read downward for a publish and upward for a delivery. The middle layer is the load-bearing one: it knows nothing about Redis, which is what lets `SM009` keep standing while the plugin supplies the connection.

The framework owns the bus: the channel registry, the wire format, and the filter that stops a worker acting on its own broadcast coming back. It knows nothing about how a message travels. Whoever owns a shared backend installs a transport on it — `background_tasks` does, with the Redis connection it already configures for Celery.

With no transport installed the bus is honest in-process pub/sub, which is the behaviour that predates it.

## Subscribing

Override `register_invalidations`. Handlers may be sync or async, and may only forget:

```python
_TOTALS: TTLCache = TTLCache(maxsize=1000, ttl=60)


class OrdersModule(ModuleBase):
    def register_invalidations(self, bus: InvalidationBus, app: FastAPI) -> None:
        bus.subscribe("orders.totals", lambda inv: _TOTALS.pop(inv.key, None))
```

Channel naming is `<module>.<cache>`. `Invalidation.key` is `None` for "forget the whole channel".

There is no `unsubscribe`, and subscribing the same callable twice runs it twice — subscriptions are made once at boot and last the life of the process. A handler may call `subscribe` during dispatch; the new handler takes effect from the *next* publish, because `_dispatch` walks a snapshot (it used to walk the live list, which let a self-re-arming handler wedge the event loop).

**The key is a string on the wire.** If your cache is keyed by anything else — `users` keys by `uuid.UUID` — convert on the way in, or the handler pops a key that is not there and the whole mechanism is a silent no-op that unit tests of the publisher still pass. See `users.accounts.session_revocation._cache_key`.

## Publishing

There is no hook: reach the bus at `request.app.state.sm.invalidation`.

```python
user.session_version = int(user.session_version or 0) + 1
db.on_commit(lambda: publish_revocation(request.app, user.id))
```

Publish from a **`db.on_commit` callback**, not inline. Two reasons, both learned the hard way:

- Clearing before the row is durable means a failed commit leaves the cache empty and the counter unchanged, so the next read repopulates the *old* value and quietly re-admits everything the write was meant to end.
- The callback runs inside the response cycle, so the browser that pressed the button is never told it worked while this worker still honours the old value.

A transport failure never propagates. The caller has already committed; turning "Redis is unreachable" into a 500 on that request would trade a bounded staleness window for an outright failure. It logs at error, because the operator needs to know the fan-out is degraded to per-process.

## Operating it

`background_tasks` installs the transport during `on_startup`, on its own `broker_url` — which resolves as `SM_BG_TASKS_BROKER_URL` (deprecated for a Redis URL) → `SM_REDIS_URL` → stored override → the localhost default. So it always follows Celery's broker, by construction rather than by convention.

| Setting | Default | What it does |
|---|---|---|
| `SM_BG_TASKS_BROADCAST_INVALIDATIONS` | `true` | Off means every per-process cache stays stale in the other workers for its own TTL. |
| `SM_BG_TASKS_INVALIDATION_CHANNEL` | `simple_module.invalidation.<installation_id>` | Optional explicit channel. Environment → DB override → derived default. |

Every framework channel shares that one Redis channel; `Invalidation.channel` routes inside the receiving process.

The installation ID is generated once as a UUID and stored in the existing system
settings table under `host.installation_id`. Provisioning reuses the root-secret
mechanism: concurrent processes insert, then re-read the winning stored value.
It needs no schema migration and works without the settings plugin. A dedicated
ID keeps secret rotation from changing the channel. It is internal metadata, not
an editable host setting or a new environment variable. Separate databases get
separate IDs; a database clone retains its source's ID, so reset that metadata
when deliberately turning a clone into a separate installation.

Before migrations create the settings table, no ID can be shared: broadcasting
stays off (local invalidation and TTLs still work). Deferred module startup retries
after setup migrations. Database errors propagate rather than silently minting
per-process IDs. Explicit channels work independently of identity provisioning.

### Rolling upgrades (bridge removed in 0.1.0)

The current framework version is 0.0.47; the next minor release is **0.1.0**.
Until that release, derived-default processes **publish and subscribe on both**
the derived channel and the legacy global `simple_module.invalidation` channel.
This preserves old → new and new → old invalidations. The bridge registers a
`simple_module_core.deprecation` warning with `remove_in="0.1.0"`, enforced by
`host/tests/test_deprecation_expiry.py`. Duplicate deliveries are possible;
handlers must remain forget-only and tolerate them.

Redis Pub/Sub ignores logical database indices. While the bridge exists,
**legacy traffic can still cross installations**, including between new processes
via the global channel. Automatic per-installation names need no operator setup,
but complete isolation arrives when the bridge is removed. For immediate isolation,
set an explicit unique channel on all replicas of an app. Explicit env or stored
channels use only that channel and do not enable the global bridge; keep existing
custom channel overrides through an upgrade. After the bridge's removal, finish
upgrading old replicas before expecting invalidations between versions.

> **Anyone who can `PUBLISH` to the channel can clear these caches.** The wire format is unauthenticated and unsigned by design — it carries no secrets, and its only direct effect is to make a worker re-read a row. A single well-formed message with `"key": null` empties a whole channel's cache in every worker, so the blast radius of a stray `redis-cli publish`, or of a co-tenant app left on the default channel name, is extra database reads until the caches warm again. The primary shape is denial of service, not an authentication bypass.
>
> One caveat, because it is not obvious and it is not only an attacker's to trigger: an empty cache is also what exposes `UsersAuthProvider._version_still_current`'s fail-open branch. A cache **hit** is an in-memory comparison that cannot fail open; only a **miss** reaches the DB read, whose `except Exception` deliberately returns `True` so a database blip does not sign everyone out. So a flushed cache plus a simultaneously failing database admits sessions that a warm cache would have refused. This composition predates the bus — a 30-second TTL expiry, or a cold cache after a deploy, reaches the same branch — and the bus adds one more route to it, including a whole-channel clear that reaches every user at once rather than one at a time. Treat the Redis instance as trusted infrastructure; the temporary global bridge has the cross-installation limits described above.

Failure behaviour, all deliberate:

- **Redis unreachable at boot** — the app boots, logs a warning naming the consequence, and the listener retries with capped backoff. A web worker that can serve every request must not fail to start over a degraded accelerator.
- **Redis lost later** — same warning once, then reconnects. Giving up after the first failure would be the original bug wearing a warning message. Confirmed against a real `kill -9` and restart; a message published during the gap is lost, because pub/sub has no replay.
- **A malformed message** — dropped at debug. A shared Redis server carries other people's traffic — and per the warning above, the logical database index does not keep it off this channel — so a listener that died on one payload would take invalidation down for the life of the process.
- **A handler raises** — logged, and the remaining handlers still run. One module's broken eviction is not a reason for another's cache to stay stale.
- **Redis accepts connections but stops answering** — bounded on both sides, and the two needed different fixes. The *publish* carries its own one-second `asyncio.timeout` because it runs inside the response cycle of the request that made the write, so an unbounded publish would hang a password change. The *listener* needed `socket_timeout` plus a `health_check_interval` PING: `socket_connect_timeout` bounds only the connect, so on a mute or half-open socket `subscribe()` waited on a read with no deadline — the listener hung before it had ever raised, never warned, and never reconnected, while the boot log claimed the transport was up. That was a real defect, found by QA after the feature shipped; `test_bg_invalidation_degraded.py` now fails without the fix.
- **One slow handler delays every channel** — the listener awaits each `deliver` inline, so a handler that blocks for three seconds holds up the next messages on *all* channels, not just its own. Handlers are meant to be a `pop`; anything slower belongs in a task.

### Celery worker processes

The Celery runner resolves host settings with `merge_host_settings`, then reads
or provisions the same installation ID from that host database and resolves the
same default channel as the web app. An explicit channel still wins.

A standalone worker never builds the FastAPI app, so it installs no transport: it publishes nothing and hears nothing. Same documented limit as `bind_event_bus`. A task that invalidates a cache should go through the API or accept the TTL.

### Tests

`simple_module_test` sets `SM_BG_TASKS_BROADCAST_INVALIDATIONS=false` (via `setdefault`) so no suite opens a pub/sub listener against a broker it doesn't have. A test that wants the transport sets the variable, or drives `RedisInvalidationTransport` directly. The transport is covered at three levels: `test_bg_invalidation.py` (fake client — retry, timeout, teardown logic), `test_bg_invalidation_redis.py` (real `redis-server` — round trip, origin filter, channel isolation), and `test_bg_invalidation_degraded.py` (broker refused or mute). `tests/integration/test_invalidation_cross_process.py` covers two real worker processes, with a control arm that reproduces the bug when broadcasting is off.

## Still per-process

`file_storage`'s aggregate cache remains per-process. Role overlays (`permissions.role_grants`), module settings (`settings.modules`, keyed by package) and feature flags (`feature_flags.overrides`, both scopes) subscribe through their modules' `register_invalidations` hooks. Their refresh tasks start and stop with module lifespan.

## Concurrent cache fills

`simple_module_core.singleflight.SingleFlight` serializes in-process fills for
one cache key. Keep one helper per app/cache and use `async with flight.hold(key)`
on a miss. Recheck the cache after acquiring the lock: an earlier reader may
already have filled it. Different keys proceed independently; idle keys are
removed after the final caller leaves. Failure or cancellation releases the
lock, so a waiter can retry without a cached failed task.

The lock does not version or invalidate cached data. Authorization caches must
also compare their invalidation epoch before storing a DB read, and retry
against a fresh session if the epoch changed. `simple_module_core.singleflight.fill`
is that loop:

```python
return await fill(
    lambda: read_from_db(key),
    epoch=lambda: _epoch,  # bumped by every forget
    store=lambda value: cache.__setitem__(key, value),
    cached=lambda: cache.get(key, MISS),  # MISS: nothing cached; None is a value
)
```

It reads at most `MAX_FILL_ATTEMPTS` (3) times. When every read raced an
invalidation it returns the last read **uncached** rather than loop while
invalidations keep arriving. That answer is not guaranteed to be newer than an
invalidation that landed during it: it is what an uncached read racing a
concurrent change would return, and it is never stored. Tenant memberships,
tenant subdomain lookups and direct permission grants use it inside their
per-key `SingleFlight` (subdomain lookups without one); their existing TTLs
still bound staleness from missed cross-worker invalidations. The users
session-version cache has not yet adopted the helper.

Give each kind of key its own channel. A handler that dispatches on a key
prefix misreads any key of the other kind that happens to start with it (the
tenants module keeps user ids on `tenants.membership` and slugs on
`tenants.hosts` for this reason).
