# simple_module_db

Database layer for the [simple_module](https://github.com/antosubash/simple_module_python) framework. Provides a per-module `Base`, an async SQLAlchemy/SQLModel session, standard mixins, and an auto-commit-on-flush listener that removes manual `session.commit()` calls from service code.

## Install

```bash
pip install simple_module_db
```

## What it provides

- `create_module_base("<module_name>")` — a module-scoped declarative `Base` with its own `MetaData`. All modules share the host's single schema, so `__tablename__` should be prefixed with the module name (e.g. `users_user`) to avoid collisions.
- Per-request `RequestSession` (`get_db`) that commits pending writes before the response and rolls back read-only requests.
- `session.on_commit(callback)` for synchronous or asynchronous cache refreshes that must only run after a successful request commit.
- Mixins in `simple_module_db.mixins`: `AuditMixin` (created_at/updated_at), `SoftDeleteMixin` (auto-filtered unless `stmt.execution_options(include_deleted=True)`), `MultiTenantMixin`, `VersionedMixin`.
- `DatabaseState` container used by the framework to avoid global mutable state.

## Usage

```python
# modules/orders/orders/models.py
from simple_module_db import AuditMixin, SoftDeleteMixin, create_module_base
from sqlmodel import Field

Base = create_module_base("orders")


class Order(Base, AuditMixin, SoftDeleteMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(index=True, foreign_key="users_user.id")
    total_cents: int
```

In a service:

```python
from simple_module_db import RequestSession, get_db

async def create_order(session: RequestSession = Depends(get_db), ...):
    order = Order(customer_id=..., total_cents=...)
    session.add(order)
    await session.flush()   # assigns order.id; commit happens before the response
    session.on_commit(order_cache.refresh)
    return order
```

Never call `session.commit()` — the framework handles it.

## Depends on

- `simple_module_core`, `sqlalchemy[asyncio]`, `sqlmodel`, `alembic`, `asyncpg`, `aiosqlite`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
