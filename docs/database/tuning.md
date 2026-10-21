# Database pool and timeout tuning

The application PostgreSQL engine uses `SM_DB_POOL_TIMEOUT=30` seconds to wait
for a pooled connection and `SM_DB_CONNECT_TIMEOUT=10` seconds to connect.
`SM_DB_STATEMENT_TIMEOUT_MS=0` and `SM_DB_IDLE_IN_TX_TIMEOUT_MS=0` omit their
PostgreSQL startup parameters; positive values set limits in milliseconds.
All four settings require a process restart. SQLite ignores these settings,
including pool timeout. Alembic and the pre-app settings read do not use them.

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
