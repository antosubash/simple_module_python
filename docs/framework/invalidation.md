# Cache invalidation

`InvalidationBus` tells the *other* worker processes that something they have cached stopped being true. It is in-process by default and cross-process when a transport is installed.

It is not `EventBus` and not a queue. `EventBus` carries domain events inside one process and its handlers may do anything; this carries "forget an entry" and its handlers may only forget. Neither persists, retries, or guarantees delivery — so **every consumer keeps a TTL as its floor** and treats the bus as an accelerator over it. Work that must happen exactly once belongs in a Celery task.

## The problem it solves

Several modules cache a row that is cheap to read and expensive to read *often*:

| Cache | Read on | Expires after | Owner |
|---|---|---|---|
| `User.session_version` | nearly every authenticated request | 30s | `users.session_version_cache` |
| aggregate storage size | the files index | 30s | `file_storage` |
| hydrated settings objects | every request that reads a setting | **never** | `settings` |

The first two share one failure shape: the worker that performed the write dropped its own entry immediately and **every other worker kept serving the stale value until its own entry expired**. Acceptable for "sign out everywhere"; much less so for a password change made because an account is believed compromised ([#318](https://github.com/antosubash/simple_module_python/issues/318)).

The third is worse, and is worth stating separately because it is easy to assume it has a TTL too. `settings.reload.apply_changes_and_reload` swaps the settings object on `app.state.<module>` in the worker that handled the save and announces it on the **in-process** `EventBus`. There is no TTL and no re-read, so every other worker serves the old configuration **until it is restarted** — an admin editing a setting on a four-worker deployment changes it for one worker in four. That needs a re-read rather than a `pop`, which is why it is not wired here (see *Still per-process*).

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

**The key is a string on the wire.** If your cache is keyed by anything else — `users` keys by `uuid.UUID` — convert on the way in, or the handler pops a key that is not there and the whole mechanism is a silent no-op that unit tests of the publisher still pass. See `users.session_revocation._cache_key`.

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

`background_tasks` installs the transport during `on_startup`, on its own `broker_url` — which resolves as stored override → `SM_BG_TASKS_BROKER_URL` (deprecated) → `SM_REDIS_URL` → the localhost default. So it always follows Celery's broker, by construction rather than by convention.

| Setting | Default | What it does |
|---|---|---|
| `SM_BG_TASKS_BROADCAST_INVALIDATIONS` | `true` | Off means every per-process cache stays stale in the other workers for its own TTL. |
| `SM_BG_TASKS_INVALIDATION_CHANNEL` | `simple_module.invalidation` | **Rename it for every app on a shared Redis server.** See the warning below — the database index does not isolate this. |

Every framework channel shares that one Redis channel; `Invalidation.channel` routes inside the receiving process.

> **A stored override beats the environment.** `settings.hydrate.hydrate_settings` passes DB values to the settings class as *init args*, and pydantic-settings ranks init args above its env source — so once `background_tasks.broadcast_invalidations` has a row in the settings store (written from the admin UI, or by `smpy settings import-from-env`), the env var above stops having any effect after boot hydration. This inverts the precedence CLAUDE.md states (`env → DB → default`) and is not specific to these two fields: it applies to every env-readable module setting, `broker_url` included. Check the settings screen, not just the container's environment, when a knob appears not to work.

> **Redis pub/sub ignores the database index.** A publisher on `redis://host/0` and a subscriber on `redis://host//1` with the same channel name *do* reach each other — pub/sub is server-global, not per-database. So the `dev-services` convention of giving each repo its own logical DB (this one owns 4 and 5) isolates keys but **not** invalidations: two installs left on the default channel name will clear each other's caches, and each will see the other's user ids on the wire. Verified by experiment. Rename the channel per app; do not rely on the DB number.

> **Anyone who can `PUBLISH` to the channel can clear these caches.** The wire format is unauthenticated and unsigned by design — it carries no secrets, and its only direct effect is to make a worker re-read a row. A single well-formed message with `"key": null` empties a whole channel's cache in every worker, so the blast radius of a stray `redis-cli publish`, or of a co-tenant app left on the default channel name, is extra database reads until the caches warm again. The primary shape is denial of service, not an authentication bypass.
>
> One caveat, because it is not obvious and it is not only an attacker's to trigger: an empty cache is also what exposes `UsersAuthProvider._version_still_current`'s fail-open branch. A cache **hit** is an in-memory comparison that cannot fail open; only a **miss** reaches the DB read, whose `except Exception` deliberately returns `True` so a database blip does not sign everyone out. So a flushed cache plus a simultaneously failing database admits sessions that a warm cache would have refused. This composition predates the bus — a 30-second TTL expiry, or a cold cache after a deploy, reaches the same branch — and the bus adds one more route to it, including a whole-channel clear that reaches every user at once rather than one at a time. Treat the Redis instance as trusted infrastructure and give each app its own channel.

Failure behaviour, all deliberate:

- **Redis unreachable at boot** — the app boots, logs a warning naming the consequence, and the listener retries with capped backoff. A web worker that can serve every request must not fail to start over a degraded accelerator.
- **Redis lost later** — same warning once, then reconnects. Giving up after the first failure would be the original bug wearing a warning message. Confirmed against a real `kill -9` and restart; a message published during the gap is lost, because pub/sub has no replay.
- **A malformed message** — dropped at debug. A shared Redis server carries other people's traffic — and per the warning above, the logical database index does not keep it off this channel — so a listener that died on one payload would take invalidation down for the life of the process.
- **A handler raises** — logged, and the remaining handlers still run. One module's broken eviction is not a reason for another's cache to stay stale.
- **Redis accepts connections but stops answering** — bounded on both sides, and the two needed different fixes. The *publish* carries its own one-second `asyncio.timeout` because it runs inside the response cycle of the request that made the write, so an unbounded publish would hang a password change. The *listener* needed `socket_timeout` plus a `health_check_interval` PING: `socket_connect_timeout` bounds only the connect, so on a mute or half-open socket `subscribe()` waited on a read with no deadline — the listener hung before it had ever raised, never warned, and never reconnected, while the boot log claimed the transport was up. That was a real defect, found by QA after the feature shipped; `test_bg_invalidation_degraded.py` now fails without the fix.
- **One slow handler delays every channel** — the listener awaits each `deliver` inline, so a handler that blocks for three seconds holds up the next messages on *all* channels, not just its own. Handlers are meant to be a `pop`; anything slower belongs in a task.

### Celery worker processes

A standalone worker never builds the FastAPI app, so it installs no transport: it publishes nothing and hears nothing. Same documented limit as `bind_event_bus`. A task that invalidates a cache should go through the API or accept the TTL.

### Tests

`simple_module_test` sets `SM_BG_TASKS_BROADCAST_INVALIDATIONS=false` (via `setdefault`) so no suite opens a pub/sub listener against a broker it doesn't have. A test that wants the transport sets the variable, or drives `RedisInvalidationTransport` directly. The transport is covered at three levels: `test_bg_invalidation.py` (fake client — retry, timeout, teardown logic), `test_bg_invalidation_redis.py` (real `redis-server` — round trip, origin filter, channel isolation), and `test_bg_invalidation_degraded.py` (broker refused or mute). `tests/integration/test_invalidation_cross_process.py` covers two real worker processes, with a control arm that reproduces the bug when broadcasting is off.

## Still per-process

Only `users.session_version` is wired so far. `file_storage`'s aggregate cache and `settings`' hot-swap have the same staleness shape and the same fix available; they are separate changes because each needs its own decision about what "forget" means for it — a settings hot-swap in particular has to *re-read*, not just drop, so it needs more than a `pop`.
