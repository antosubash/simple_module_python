# simple_module_audit_log

Automatic field-level audit trail for all SQLModel entities in [simple_module](https://github.com/antosubash/simple_module_python) apps. Every create / update / delete / soft-delete is captured in `audit_log.audit_entries` with the changed fields, the user who made the change, and the request correlation id — no instrumentation required in module code.

## Install

```bash
pip install simple_module_audit_log
```

Add `simple_module_audit_log` to your host's dependencies and the entry point will be discovered automatically.

## What it provides

- Two-phase capture (`before_flush` snapshots diffs, `after_flush_postexec` resolves DB-assigned primary keys) so integer-PK entities record the real id, not the empty string.
- `AuditEntry` SQLModel table with indexed `entity_type`, `entity_id`, `user_id`, `created_at` columns.
- `GET /api/audit_log/` REST endpoint with `entity_type`, `entity_id`, `action`, `user_id`, `from_date`, `to_date`, paging filters.
- `/audit_log` Inertia browse page with the same filter set rendered as a table, gated by the `audit_log.view` permission.
- Opt-outs: set `__audit_exclude__ = True` on a model to skip it entirely, or `__audit_exclude_fields__ = {"password_hash"}` to skip specific columns. `AuditMixin` / `SoftDeleteMixin` bookkeeping fields are excluded automatically.

## Usage

Install the module and grant the `audit_log.view` permission to your admin role. Audit entries appear automatically for every entity that does not opt out.

To exclude a sensitive column:

```python
from typing import ClassVar
from sqlmodel import Field
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin

Base = create_module_base("auth")


class Credential(Base, AuditMixin, table=True):
    __audit_exclude_fields__: ClassVar[set[str]] = {"password_hash"}

    id: int | None = Field(default=None, primary_key=True)
    user_id: str
    password_hash: str
```

To opt a whole table out:

```python
class Cache(Base, table=True):
    __audit_exclude__ = True
    ...
```

## License

MIT
