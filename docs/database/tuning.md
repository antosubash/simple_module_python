# Database pool and timeout tuning

## Supported providers

`detect_provider()` parses the SQLAlchemy URL's backend name. It recognises
`sqlite`, `sqlite+aiosqlite`, `sqlite+pysqlite`, `postgresql`,
`postgresql+asyncpg`, `postgresql+psycopg` and `postgresql+psycopg2`.
The legacy `postgres://` alias is still recognised as PostgreSQL by detection;
use `postgresql` for SQLAlchemy engine URLs. Detection identifies a provider,
not whether a driver supports async engines: the default application engine
needs an async driver such as aiosqlite or asyncpg.

Other dialects raise `ValueError` naming only the dialect and supported providers,
without exposing URL credentials. They no longer receive SQLite connection
arguments or PRAGMA listeners. The same validation applies to worker engines
and Alembic's online and offline environments (#967).

## Pool and timeout settings

The application PostgreSQL engine uses `SM_DB_POOL_TIMEOUT=30` seconds to wait
for a pooled connection and `SM_DB_CONNECT_TIMEOUT=10` seconds to connect.
`SM_DB_STATEMENT_TIMEOUT_MS=0` and `SM_DB_IDLE_IN_TX_TIMEOUT_MS=0` omit their
PostgreSQL startup parameters; positive values set limits in milliseconds.
All four settings require a process restart. SQLite ignores these settings,
including pool timeout. Alembic and the pre-app settings read do not use them.

Set asyncpg timeouts through the host settings, not URL query parameters.
Asyncpg receives server settings; psycopg/psycopg2 receive libpq startup options.
PgBouncer transaction pooling rejects startup parameters such as these timeout
settings. Leave the millisecond settings at zero and configure limits on the
server or database role when using that mode.

Background workers inherit the resolved host timeouts. Their sync engine and
each outbox thread's async engine have separate pools, defaulting to size 2,
overflow 3 and recycling after 1800 seconds. Size the database connection budget
for all processes and outbox threads. Override these through
`SM_BG_TASKS_DB_POOL_SIZE`, `SM_BG_TASKS_DB_MAX_OVERFLOW` and
`SM_BG_TASKS_DB_RECYCLE`. Optional `SM_BG_TASKS_DB_STATEMENT_TIMEOUT_MS`
overrides the host statement limit, including zero to omit it. Restart workers
after changing these settings.

## Supplying an engine and session factory

`create_app(settings, database=state)` accepts a prebuilt `DatabaseState`.
Alternatively, `database=make_database` calls a synchronous factory once with
the resolved `Settings`, and uses the returned state. `build_host_app` accepts
the same argument. Both forms bypass the default `init_db()` call while keeping
framework session listeners, tenancy policy, principal bindings, database health
checks and development query statistics.

For a custom engine (for example SQLAlchemy's `async_creator`) construct the
state with `RequestSession`, a dedicated sync session class, and the session
factory reference used by `independent_session(session)`:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from simple_module_db import DatabaseState, RequestSession
from simple_module_db.session import SESSION_FACTORY_KEY


def make_database(settings):
    # connect is your async DBAPI connection creator.
    engine = create_async_engine(settings.database_url, async_creator=connect)

    class SyncSession(Session):
        pass

    factory = async_sessionmaker(
        engine,
        class_=RequestSession,
        sync_session_class=SyncSession,
        expire_on_commit=False,
    )
    factory.configure(info={SESSION_FACTORY_KEY: factory})
    return DatabaseState(engine, factory, sync_session_class=SyncSession)
```

The supplied factory controls session routing, including read replicas. The
state's `engine` is the primary engine used for migration checks and process
services. Configure extra binds and their engine policies in your factory.
Custom engines also own their driver options and SQLite PRAGMA setup; use
`init_db()` when its standard engine configuration is sufficient.

**Ownership:** omitting `database` preserves the default engine and lifespan
cleanup, including cleanup after startup failure. Supplied states and factory
results are caller-owned. Retain them and dispose every associated engine
after the app stops, including on startup failure; the framework never disposes
them. Do not share a state between apps with different tenancy or principal
policies, since app construction binds those policies to the state.
