# simple_module_audit_log

Automatic field-level audit trail for all SQLModel entities in [simple_module](https://github.com/antosubash/simple_module_python) apps. Every create / update / delete / soft-delete is captured in the `audit_log_audit_entry` table with the changed fields, the user who made the change, and the request correlation id — no instrumentation required in module code.

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


## Credential redaction

Set `__audit_redact_fields__: ClassVar[set[str]] = {"credential"}` on a
model to keep a field in the audit diff while replacing every recorded `old`
and `new` value with `[redacted]`. Unlike `__audit_exclude_fields__`, which
omits a field entirely, redaction preserves the fact that it changed.
Exclusion takes precedence. A redacted primary key also masks `entity_id`.

For row-dependent rules, define a static `__audit_redact_row__(row)` method
returning a set of field names. ORM capture evaluates the current and pre-edit
column dictionaries and redacts fields identified by either. Bulk and manual
capture pass `None`; the predicate must conservatively return every field
that could hold a credential when row context is unavailable. Manual capture
accepts the mapped class or its registered class name to apply its policy.

Built-in policies cover stored secret settings, user password hashes, OAuth
credentials, tenant invitation hashes, bearer tokens, lease ownership tokens and auth refresh outcomes.
Settings use the same secret rule as the settings UI. Non-secret ORM settings
retain their values; bulk settings values are always redacted because the
statement may affect rows with different keys or prior values. API token
hashes remain excluded from automatic diffs.

Migration `b8d4f2a6c901` hardens existing entries, conservatively redacting all
historical settings values because old diffs may lack the key or type needed
to classify them. It also masks historical credential primary-key identities.
Its downgrade is a no-op: credential values cannot be recovered. Operators
should rotate credentials saved through the settings UI on earlier versions;
the migration does not rewrite backups or previously exported audit data.
