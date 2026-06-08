# Session lifecycle

Each request opens exactly one `AsyncSession`. The framework commits only when there are pending writes; read-only requests rollback. **Service code should not call `session.commit()` directly.**

## The `get_db` dependency

```python
# simple_module_db.deps
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    factory = request.app.state.sm.db.session_factory
    async with factory() as session:
        try:
            yield session
            if _has_pending_writes(session):
                await session.commit()
            else:
                await session.rollback()
        except Exception:
            await session.rollback()
            raise
```

Usage in endpoints:

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from simple_module_db.deps import get_db

SessionDep = Annotated[AsyncSession, Depends(get_db)]

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

To distinguish "this request wrote something" from "this request only read", an `after_flush` event listener sets `session.info["has_writes"] = True`. The dependency checks:

```python
if session.info.get("has_writes") or session.new or session.dirty or session.deleted:
    await session.commit()
else:
    await session.rollback()
```

Why both? `session.new/dirty/deleted` show **pending** writes that haven't flushed yet; `has_writes` catches the case where writes flushed but were already synced. Together they cover every path to "we touched the DB with intent to change it."

## Why not always commit?

- **Cheaper.** A rollback on a clean session is a single Postgres message; a commit with no writes still goes through two-phase round-trips on some drivers.
- **Observability.** The write/read distinction is useful in profiling and logs — you can answer "how many requests mutated data?" without guessing.
- **Safety.** If a GET handler accidentally stages a write (rare, but happens with `session.merge`), the rollback prevents silent persistence.

## Why service code shouldn't commit

The per-request session is **owned** by the dependency. If your service calls `commit()` mid-request, two problems arise:

1. The dependency commits again on exit — harmless but confusing.
2. If a later step in the request fails, the partial writes are already persisted and can't be rolled back.

Instead, **flush** when you need a DB-assigned value (e.g. an auto-generated `id`):

```python
async def create(self, data: OrderCreate) -> OrderOut:
    order = Order(**data.model_dump())
    self.session.add(order)
    await self.session.flush()     # populates order.id, stays inside the transaction
    # further logic can see order.id but won't persist until the dependency commits
    return OrderOut.model_validate(order)
```

Flushing sends the INSERT but keeps the transaction open. Rollback still works until the dependency commits.

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
| Inside an endpoint handler / service, done with work | nothing — dependency commits on exit |
| Outside a request (worker, CLI, lifespan) | explicit `async with session.begin():` |
| A handler that reads-only but wants to persist an audit row | stage the row; the dependency detects pending writes and commits |
| A handler that must explicitly discard partial changes | `raise`ing propagates to the dependency, which rolls back |

If you find yourself writing `await session.commit()` inside a service, step back — there's a cleaner way using flush or a dedicated transactional helper.
