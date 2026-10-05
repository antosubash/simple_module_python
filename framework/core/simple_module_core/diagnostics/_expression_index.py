"""Expression-index diagnostics (SM026).

SQLAlchemy cannot reflect expression indexes (``lower(email)``) on SQLite, so
autogenerate and ``alembic check`` silently skip them there and report a clean
diff. That is "unverified", not "clean": on Postgres the same index is either
missing from the history or drifted. SM026 says so whenever the configured
database is SQLite and any module model declares such an index.

Duck-typed on SQLAlchemy ``Table``/``Index`` objects (core does not depend on
SQLAlchemy).
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

logger = logging.getLogger(__name__)


def index_is_expression_based(index: Any) -> bool:
    """True when any element of ``index`` is an expression rather than a plain column.

    A plain ``Column`` is attached to its table; a ``text()`` or function
    element is not.
    """
    return any(getattr(expr, "table", None) is None for expr in index.expressions)


def find_expression_indexes(tables: Iterable[Any]) -> list[tuple[str, str]]:
    """Return sorted ``(table name, index name)`` pairs for expression indexes."""
    found = {
        (table.name, index.name or "<unnamed>")
        for table in tables
        for index in table.indexes
        if index_is_expression_based(index)
    }
    return sorted(found)


def module_all_tables(mod: ModuleBase) -> list[Any]:
    """Every table declared in the module's ``models`` submodule."""
    pkg = type(mod).__module__.rsplit(".", 1)[0]
    try:
        models = importlib.import_module(f"{pkg}.models")
    except ModuleNotFoundError:
        return []
    except Exception:  # pragma: no cover - a broken models module fails elsewhere, loudly
        logger.debug("Could not import %s.models for SM026", pkg, exc_info=True)
        return []
    seen: dict[str, Any] = {}
    for value in vars(models).values():
        table = getattr(value, "__table__", None)
        if isinstance(value, type) and table is not None and hasattr(table, "indexes"):
            seen.setdefault(table.name, table)
    return list(seen.values())


def check_expression_indexes_unverifiable(
    tables: Iterable[Any], dialect: str | None, module_name: str
) -> list[Diagnostic]:
    """SM026: INFO on SQLite when the models declare indexes it cannot verify."""
    if dialect != "sqlite":
        return []
    found = find_expression_indexes(tables)
    if not found:
        return []
    names = ", ".join(f"{idx} ({tbl})" for tbl, idx in found)
    return [
        Diagnostic(
            level=DiagnosticLevel.INFO,
            code="SM026",
            message=(
                f"SQLite cannot reflect expression indexes, so autogenerate and "
                f"`alembic check` cannot verify {names}; a clean diff here says nothing "
                f"about them"
            ),
            module_name=module_name,
            suggestion=(
                "Add them to a revision by hand and verify on Postgres: "
                "`make migrations-roundtrip-pg`"
            ),
        )
    ]


__all__ = [
    "check_expression_indexes_unverifiable",
    "find_expression_indexes",
    "index_is_expression_based",
    "module_all_tables",
]
