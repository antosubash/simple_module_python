---
trigger: model_decision
description: Database bases, mixins, AwareDateTime, SQLite/Postgres sessions, multi-tenancy isolation, and Alembic migration rules for simple_module_python.
---

## Database

- Per-module `Base` via `create_module_base("<name>")`; every module owns its
  `MetaData` but all tables share one schema. Prefix `__tablename__` with the
  module name (`orders_order`); the scaffold does it, nothing enforces it.
- Mixins in `simple_module_db.models.mixins`: `AuditMixin`, `SoftDeleteMixin`,
  `MultiTenantMixin`, `VersionedMixin`. Soft-delete and tenant filters cover
  every statement shape. Bypass with `execution_options(include_deleted=True)`;
  purge with `hard_delete(session, obj)`. `docs/database/mixins.md`.
- A bare `datetime` field already maps to a UTC-aware type. When you declare
  an explicit column type, use `sa_type=AwareDateTime()`
  (`simple_module_db.models.types`), never `DateTime(timezone=True)`, which reads back
  naive on SQLite.
- SQLite runs with WAL (file DBs), `busy_timeout` and **`foreign_keys=ON`**:
  both sides of an FK need the same column type (`sa.Uuid` vs fastapi-users'
  `GUID` differ on SQLite) and parents must be flushed before children.
- **Sessions.** The request session (`get_db`) commits in
  `CommitBeforeResponseMiddleware` only if something was written (ORM flush or
  `session.execute(update/insert/delete)`); otherwise it rolls back. Raw
  `text("UPDATE …")` needs `mark_written(session)`. Service and request code
  must not call `session.commit()`; flush when you need DB-assigned values. Use
  `session.on_commit(cb)` for post-commit side effects. `docs/database/sessions.md`.
- **Tenancy fails closed.** With `multi_tenant` on, a query or insert on a
  `MultiTenantMixin` model with no current tenant raises `TenantIsolationError`.
  Cross-tenant code says so with `all_tenants()` /
  `execution_options(all_tenants=True)`; jobs act for one tenant with
  `tenant_context(id)` (both in `simple_module_db.scoping.tenancy`). Off, rows are
  stamped `default_tenant` when set, else `DEFAULT_TENANT_ID` (`"default"`).
  Unique keys on tenant tables must include `tenant_id` (`SM024`). Tenant-level
  routes act on the *active* tenant, never a tenant id from the URL. The `tenants`
  module owns memberships and `app.state.tenant_resolver` (`SM025` if missing). Map tenant
  roles with `tenant_role(TenantRole.MEMBER)` from `simple_module_core.access.tenancy`,
  never by importing `tenants`. `docs/framework/multi-tenancy.md`.
- **Migrations** live in `host/migrations/versions/`, never in module packages.
  `host/migrations/env.py` builds metadata from every installed module. The
  history has several roots and heads (`host/tests/test_migration_graph.py`
  pins them; update it with any new root or head), so apply with
  `upgrade heads` (`make migrate`) and autogenerate on a named branch:

  ```
  uv run --project host alembic -c host/alembic.ini revision --autogenerate \
      -m "<msg>" --head <branch_label>@head
  ```

  A module's first revision sets `branch_labels`. Labels are named targets, not
  per-module rollbacks: `downgrade <label>@base` also unwinds everything above
  and beneath it on that root. `docs/database/migrations.md`.
- Postgres extensions: override `ModuleBase.db_extensions()`; `LTree`/`TSVector`
  types are `TEXT` on SQLite; tests needing Postgres carry
  `@pytest.mark.postgres`. `docs/database/extensions.md`.
