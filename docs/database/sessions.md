# Session lifecycle

Each request opens exactly one `AsyncSession`. The framework commits only when there are pending writes; read-only requests end their transaction with a rollback that preserves loaded attributes. **Service code should not call `session.commit()` directly.**

## The `get_db` dependency

`get_db` yields a request session and enlists it with
`CommitBeforeResponseMiddleware`. At `http.response.start`, before headers or
body bytes leave the server, the middleware commits pending writes or closes a
read-only transaction. Closing rolls back and releases the connection without
expiring or detaching loaded ORM objects. A streaming body or background task
can read already-loaded attributes without database IO; unloaded attributes
still require an explicit async load.

If commit fails, the framework rolls back and unwinds the original response,
including its streaming body and background tasks, then sends a JSON 500.
Those tasks do not run for a failed request commit (#807).

The dependency finalizes again on exit to persist writes made during a
successful stream or background task. The session remains usable after
read-only finalization, including for later writes (#808). Without the
middleware, finalization happens when the dependency exits.

Usage in endpoints:

```python
from typing import Annotated
from fastapi import Depends
from simple_module_db import RequestSession
from simple_module_db.deps import get_db

SessionDep = Annotated[RequestSession, Depends(get_db)]


@router.post("")
async def create_order(data: OrderCreate, session: SessionDep): ...
```

Most modules wrap `get_db` in their own `deps.py` so the service is injected rather than the raw session:

```python
# modules/orders/orders/deps.py
from orders.service import OrderService


def _order_service(session: SessionDep) -> OrderService:
    return OrderService(session)


OrderServiceDep = Annotated[OrderService, Depends(_order_service)]
```

## The `has_writes` flag

ORM flushes and session-executed INSERT/UPDATE/DELETE statements mark the
current transaction as written. Raw SQL writes require `mark_written(session)`.
The finalizer checks both this marker and pending `new`/`dirty`/`deleted`
objects, so an already-flushed write still commits.

Write markers follow savepoint boundaries: releasing a savepoint merges its
marker into its parent; rolling it back discards only its marker. A released
child's writes still belong to its parent's rollback. If all writes were
rolled back, finalization takes the read-only path and discards outer
`on_commit` callbacks (#809). Callbacks registered inside a rolled-back
savepoint are also discarded, while callbacks outside it survive if other
writes commit. A full rollback clears all write markers and callbacks.

## Why not always commit?

- **Cheaper.** A rollback on a clean session is a single Postgres message; a commit with no writes still goes through two-phase round-trips on some drivers.
- **Observability.** The write/read distinction is useful in profiling and logs — you can answer "how many requests mutated data?" without guessing.
- A handler that stages a write, including a GET handler, takes the write path and commits. Read-only finalization is not a guard against accidental writes.

## Why service code shouldn't commit

The per-request transaction is **owned** by the framework. If your service calls `commit()` mid-request, two problems arise:

1. It bypasses commit-before-response finalization and its post-commit callbacks.
2. If a later step in the request fails, the partial writes are already persisted and can't be rolled back.

Instead, **flush** when you need a DB-assigned value (e.g. an auto-generated `id`):

```python
async def create(self, data: OrderCreate) -> OrderOut:
    order = Order(**data.model_dump())
    self.session.add(order)
    await self.session.flush()  # populates order.id, stays inside the transaction
    # further logic can see order.id but won't persist until the dependency commits
    return OrderOut.model_validate(order)
```

Flushing sends the INSERT but keeps the transaction open. Rollback still works until the dependency commits.

## Refreshing derived state after commit

The request session exposes `on_commit()` for cache invalidation and other derived
in-process state that must never reflect an uncommitted transaction:

```python
async def create(self, data: OrderCreate) -> OrderOut:
    order = Order(**data.model_dump())
    self.session.add(order)
    await self.session.flush()
    self.session.on_commit(self.order_cache.refresh)
    return OrderOut.model_validate(order)
```

Callbacks take no arguments and may be synchronous or asynchronous. The framework
runs them in registration order after a successful commit and before the response
leaves the server. It discards them when the request rolls back, when commit fails,
or when the request has no writes. A callback should refresh derived state, not
perform more database mutations.

At callback time the original transaction is already durable, so callback errors
cannot roll it back. The framework logs a `db.session.on_commit_failed` error,
continues with remaining callbacks, and preserves the successful response.

`on_commit()` is supported by framework-managed requests and independent
checkpoints. For other manually managed sessions, perform post-commit work
explicitly after the transaction block.

## Manual transactions

If you need finer control — e.g. a background worker that processes many items in its own transactions — use the `DatabaseState.session_factory` directly:

```python
from simple_module_db import DatabaseState


async def worker(db: DatabaseState):
    async with db.session_factory() as session:
        async with session.begin():
            # explicit transaction block
            session.add(...)
            # commits on exit, rolls back on exception
```

The `async with session.begin()` pattern opens a transaction you control. Use it in code that runs **outside** a request scope.

### `independent_session(source)`

Use an independent checkpoint when a write must be durable before continuing,
including before a request can fail. Examples are reserving a login attempt
before checking its password and saving invitation roles before sending mail.
Ordinary request writes still belong to `CommitBeforeResponseMiddleware`.

```python
from simple_module_db import independent_session


async def reserve_attempt(app):
    async with independent_session(app) as db:
        await reserve_slot(db)
    # The slot is durable here, even if subsequent authentication fails.
```

The source can be an app, its `app.state.sm.db.session_factory`, or a
framework-created session (which supplies that same factory). The helper opens
and closes its own short-lived session, commits on clean exit, and rolls back
and re-raises on error. It never commits or transfers the source session's
pending work. Do not call `commit()` inside the block.

On SQLite, an independent session cannot write while the request session holds uncommitted writes (there is only one writer), so call it before the request writes, as users lockout and bulk invite do.

`on_commit` callbacks run in registration order after the checkpoint commits;
rollback or commit failure discards them. Callback failures are logged without
undoing the durable checkpoint, as for request sessions.

A checkpoint cannot see uncommitted request rows. Pass identifiers and reload
objects in the independent session rather than sharing attached ORM objects.
Keep checkpoints short and open them before the request holds a write
transaction: SQLite permits only one writer, and overlapping writes can block.
Use `session_factory()` directly for read-only work or transactions needing
several explicit commit boundaries.

## Sessions and `MultiTenantMixin`

The active tenant is carried in the `current_tenant_id` contextvar (set by `TenantMiddleware`, not on the session). The tenant listeners read that contextvar to filter SELECTs and stamp INSERTs. Sessions stay **request-scoped** so they always run under the request's tenant context — sharing one across tenants would silently leak data.

Cross-tenant admin work runs outside a tenant-scoped request (a CLI or worker where `current_tenant_id` is unset). See [Mixins → MultiTenantMixin](/database/mixins).

## Sessions in tests

The `db_session` fixture from the `simple_module_test` plugin creates a fresh in-memory SQLite DB, creates every module's tables, stamps `alembic_version` at head, and yields an `AsyncSession`. Each test gets a fresh one — no shared state, no transaction rollback hacks.

```python
@pytest.mark.asyncio
async def test_order_insert(db_session):
    order = Order(customer_email="a@b.c", total=Decimal("1"))
    db_session.add(order)
    await db_session.flush()
    assert order.id is not None
```

For endpoint tests, use `client` or `authenticated_client` — they share the same `db_session` via dependency override, so writes performed by the handler are visible to test-side queries.

## Commit vs. flush checklist

| Situation | Call |
|---|---|
| Inside an endpoint handler / service, need DB-assigned id | `await session.flush()` |
| Inside an endpoint handler / service, done with work | nothing — middleware commits before response start |
| Outside a request (worker, CLI, lifespan) | explicit `async with session.begin():` |
| A handler that reads-only but wants to persist an audit row | stage the row; the dependency detects pending writes and commits |
| A handler that must explicitly discard partial changes | `raise`ing propagates to the dependency, which rolls back |

If you find yourself writing `await session.commit()` inside a service, step back — there's a cleaner way using flush or a dedicated transactional helper.

### SQLite admission checks

`simple_module_db.admission.serialize_sqlite_writes(db, table, on_busy=error)`
takes the SQLite writer lock with a zero-row UPDATE before a read/check/write
admission. It changes no rows and holds the lock until commit or rollback;
Postgres is a no-op, so callers keep their existing row/advisory locks. Storage
quotas and tenant seat limits use this helper (#753).

SQLite WAL serializes writers, but a SELECT in the driver's legacy transaction
mode need not start a transaction: two earlier counts can both pass. Taking the
writer lock **before counting** makes the second admission see the first one's
committed write. If a real deferred read transaction already has an older
snapshot, SQLite refuses its upgrade after another commit with
`SQLITE_BUSY_SNAPSHOT`. The helper raises the supplied admission error on SQLite
busy/locked errors; callers must roll back and retry in a fresh transaction,
never continue or retry the old snapshot. Other database errors propagate.
