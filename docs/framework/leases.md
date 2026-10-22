# Leases and semaphores

`simple_module_core.leases` gives every process the same two primitives ([#539](https://github.com/antosubash/simple_module_python/issues/539)):

- **`lease(name, ttl)`**: an exclusive lock that expires on its own. Use it to deduplicate work ("only one worker imports dataset 42") or to debounce.
- **`semaphore(name, slots, ttl)`**: at most `slots` concurrent holders, for example at most 4 downloads per remote host across every web and Celery worker.

Both are *leases*: whoever acquires one gets a random `token`, and only that token can refresh or release it. Once the TTL lapses, the old holder can do neither, even if no one else has taken it yet.

## Usage

```python
from simple_module_core.leases import LeaseNotAcquiredError, lease, semaphore

# Exclusive. Waits up to 5 s for the current holder, then raises.
async with lease("import:42", ttl=60, wait=5) as held:
    for chunk in chunks:
        await process(chunk)
        if not await held.refresh():  # extend the TTL from now
            raise RuntimeError("lost the lease")  # it expired; stop writing

# Try once, never wait.
job = lease("rebuild-index", ttl=300, blocking=False)
if await job.acquire():
    try:
        await rebuild()
    finally:
        await job.release()

# Counted slots, shared across processes.
async with semaphore("dl:example.org", slots=4, ttl=120, wait=30):
    await download(url)
```

| Member | Meaning |
|---|---|
| `token` | The owner's identity. Random unless you pass `owner=` (for example a Celery task id, so a retry of the same task can re-acquire its own lease). |
| `fence` | A number that strictly increases each time the name is acquired. Store it next to whatever the holder writes and refuse a write that carries a smaller fence: that rejects a holder that stalled past its TTL and woke up late. |
| `acquire(blocking=True, wait=None)` | Returns `True` once held. Non-blocking tries once; blocking polls with jittered back-off until it gets the lease or `wait` seconds pass (`None` waits forever). |
| `refresh(ttl=None)` | Extends the TTL from now. Returns `False` if the lease expired or moved to another owner. |
| `release()` | Returns `False` if the lease had already expired or moved on; it never releases someone else's lease. |
| `async with` | Acquires with the handle's `blocking`/`wait`, raises `LeaseNotAcquiredError` if it cannot, and releases on exit. |

A lease does not refresh itself. Pick a TTL longer than the work, or call `refresh()` from the loop that does it.

## Backends

The backend is process-global because a Celery worker has no `app.state`. `create_app` installs it when the app is built, and the worker bootstrap (`background_tasks.runner.build_runner_celery`) installs the same kind from the same settings:

| Configured | Backend | Notes |
|---|---|---|
| `SM_REDIS_URL` | `RedisLeaseBackend` (`simple_module_hosting`) | `SET NX PX` plus Lua compare-and-set for refresh and release; a semaphore is a sorted set scored by expiry against Redis `TIME`; `INCR <key>:fence` for the fence. |
| a database, no Redis | `DbLeaseBackend` (`simple_module_db`) | Rows in `sm_lease (name, slot, holder, fence, expires_at)`, primary key `(name, slot)`. Every comparison uses the database clock, so clock skew between hosts does not matter. |
| neither | `InProcessLeaseBackend` | One process only. Also what tests and eager Celery get when nothing else is configured. |

Backend errors propagate. A lease that the backend could not confirm is never reported as held. This is unlike the rate limiter, which falls back to per-process counters.

Override the backend with `configure_leases(backend)`, or pass `backend=` to a single `lease()`/`semaphore()` call. `configure_leases(None)` restores a fresh in-process backend, which is useful in test teardown.

### The `sm_lease` table

The table belongs to the framework, like `settings_setting`, so it exists whether or not any module uses leases. Its migration `d263ea727663` is its own root with the `leases` branch label (see [Migrations](../database/migrations.md)). `make migrate` (`upgrade heads`) applies it.

Rows are never deleted: a released lease is a row whose `expires_at` is in the past. That is what keeps `fence` increasing for the life of the name. A lease uses slot `0`; a semaphore uses slots `0..n-1` and keeps its fence counter in slot `-1`. Use a bounded set of names: `"dl:<host>"` is fine, a fresh UUID per request is not.

On SQLite each attempt takes the database write lock before it reads, so processes queue on `busy_timeout` instead of racing. The table works on SQLite, but production deployments with several hosts should use Postgres or Redis.
