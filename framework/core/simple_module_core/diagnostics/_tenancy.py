"""SM024: a unique key on a tenant-scoped table that ignores the tenant.

On a ``MultiTenantMixin`` table every business key is per tenant. A unique
constraint without ``tenant_id`` in it means the first tenant to claim a value
(a slug, a filename, a name) locks every other tenant out of it — and the
resulting IntegrityError tells the second tenant the value exists elsewhere.

Duck-typed on SQLAlchemy ``Table`` objects (core does not depend on
SQLAlchemy). Only tables of models that inherit ``MultiTenantMixin`` count: a
plain ``tenant_id`` column (``users_user``'s legacy one, the ``tenants``
registry's own tables) carries no isolation and no per-tenant key rule.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

logger = logging.getLogger(__name__)

TENANT_COLUMN = "tenant_id"


def _unique_keys(table: Any) -> Iterator[tuple[str, set[str]]]:
    """Yield ``(label, column names)`` for every unique key except the PK."""
    for col in table.columns:
        if col.unique and not col.primary_key:
            yield f"column '{col.name}'", {col.name}
    for constraint in table.constraints:
        if type(constraint).__name__ == "UniqueConstraint":
            cols = {c.name for c in constraint.columns}
            yield f"unique constraint {sorted(cols)}", cols
    for index in table.indexes:
        if index.unique:
            cols = {c.name for c in index.columns}
            label = f"unique index '{index.name}'"
            # Expression indexes (lower(email)) expose no plain columns; treat
            # them as not containing the tenant — they are just as global.
            yield label, cols


def check_tenant_unique_keys(tables: Iterable[Any], module_name: str) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for table in tables:
        if TENANT_COLUMN not in table.columns:
            continue
        reported: set[frozenset[str]] = set()
        for label, cols in _unique_keys(table):
            # ``unique=True`` surfaces both as a column flag and as a
            # UniqueConstraint; report each key once. Expression indexes have
            # no plain columns and are always reported.
            key = frozenset(cols)
            if TENANT_COLUMN in cols or (cols and key in reported):
                continue
            reported.add(key)
            diags.append(
                Diagnostic(
                    level=DiagnosticLevel.WARNING,
                    code="SM024",
                    message=(
                        f"Tenant-scoped table '{table.name}' has a {label} that does "
                        f"not include '{TENANT_COLUMN}' — two tenants cannot both own a value"
                    ),
                    module_name=module_name,
                    suggestion=(
                        "Make the key per tenant: add tenant_id to the constraint, "
                        "e.g. Index(..., 'tenant_id', 'slug', unique=True)"
                    ),
                )
            )
    return diags


def _is_tenant_scoped(cls: type) -> bool:
    return any(base.__name__ == "MultiTenantMixin" for base in cls.__mro__[1:])


def module_tables(mod: ModuleBase) -> list[Any]:
    """Tables of the ``MultiTenantMixin`` models in the module's ``models``."""
    pkg = type(mod).__module__.rsplit(".", 1)[0]
    try:
        models = importlib.import_module(f"{pkg}.models")
    except ModuleNotFoundError:
        return []
    except Exception:  # pragma: no cover - a broken models module fails elsewhere, loudly
        logger.debug("Could not import %s.models for SM024", pkg, exc_info=True)
        return []
    seen: dict[str, Any] = {}
    for value in vars(models).values():
        table = getattr(value, "__table__", None)
        if (
            isinstance(value, type)
            and table is not None
            and hasattr(table, "columns")
            and _is_tenant_scoped(value)
        ):
            seen.setdefault(table.name, table)
    return list(seen.values())


__all__ = ["check_tenant_unique_keys", "module_tables"]
