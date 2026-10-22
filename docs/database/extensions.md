# Extensions and column types

Postgres features that SQLite lacks are opt-in per module. The framework
creates the extension, ships the column types, and keeps SQLite working for
development and the default test suite.

## Declaring an extension

```python
class TaxonomyModule(ModuleBase):
    meta = ModuleMeta(name="taxonomy")

    def db_extensions(self) -> list[str]:
        return ["ltree"]
```

Names must match `^[a-z][a-z0-9_-]*$`. `host/migrations/env.py` (and the
scaffolded copy) calls `ensure_db_extensions(connection, modules)` after
configuring Alembic and before the transaction that runs revisions, so a
revision that adds an `ltree` column finds the extension installed. The setup
wizard runs the same `env.py`.

| Database | Behaviour |
|---|---|
| Postgres | `CREATE EXTENSION IF NOT EXISTS "<name>"` (idempotent) |
| SQLite | raises `UnsupportedDatabaseError` naming the module and extensions |
| Offline (`alembic upgrade --sql`) | the statements are emitted into the script |

`make doctor` reports `SM029` (info) when a module declares extensions and the
database is SQLite. The role running migrations needs permission to create the
extension (trusted extensions such as `ltree` and `pg_trgm` need only
`CREATE` on the database on Postgres 13+).

## Column types

`simple_module_db.types`:

| Type | Postgres | SQLite |
|---|---|---|
| `LTree` | `LTREE` (needs `db_extensions` `["ltree"]`) | `TEXT` |
| `TSVector` | `TSVECTOR` (built in) | `TEXT` |

```python
from simple_module_db.types import LTree, TSVector


class Category(SQLModel, table=True):
    path: str = Field(sa_type=LTree(), nullable=False)
    search: str | None = Field(default=None, sa_type=TSVector())
```

Operators are Postgres-only (`Category.path.op("<@")(...)`, `.op("@@")`);
guard such queries or test them under the `postgres` marker. Autogenerate
renders both as `simple_module_db.types.LTree()` and adds the import, so one
revision upgrades on Postgres and SQLite. Reflection recognises `ltree`, so
`alembic check` stays clean.

## Testing on Postgres

Mark tests that need Postgres:

```python
import pytest

pytestmark = pytest.mark.postgres
```

They are skipped unless `SM_TEST_DATABASE_URL` is a Postgres URL (see
`make test-py-pg`); the marker is registered by the `simple_module_test`
plugin. The fixtures drop and re-create `public` per test, and then re-create
every installed module's declared extensions. Under pytest-xdist each worker
runs on its own database (`<db>_gw0`, ...), which the plugin creates on first
use, so the role needs `CREATEDB`.
