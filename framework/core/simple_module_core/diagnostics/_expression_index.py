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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase

logger = logging.getLogger(__name__)


_ORDERING_MODIFIERS = frozenset({"asc_op", "desc_op", "nulls_first_op", "nulls_last_op"})


def unwrap_ordering(expr: Any) -> Any:
    """``expr`` without its ``desc()``/``asc()``/``nulls_first()``/``nulls_last()`` wrappers."""
    while getattr(getattr(expr, "modifier", None), "__name__", None) in _ORDERING_MODIFIERS:
        expr = expr.element
    return expr


def _is_column(expr: Any) -> bool:
    """A column, possibly wrapped in ``desc()``/``asc()``/``nulls_last()``.

    SQLite reflects ``created_at DESC`` as the column ``created_at`` and Alembic
    compares it as one (GH #869), so an ordering keeps an element a column. A
    plain ``Column`` is attached to its table; ``sa.column("x")`` is a named,
    non-literal column; ``text()``, ``literal_column()``, a function or a bare
    string label are expressions.
    """
    expr = unwrap_ordering(expr)
    if hasattr(expr, "element"):
        # Still wraps something once the ordering is gone: a label over an
        # arbitrary expression (``lower(email).label("x")``) or ``sa.desc("col")``'s
        # bare-string label. A column wraps nothing.
        return False
    return getattr(expr, "table", None) is not None or getattr(expr, "is_literal", None) is False


def index_is_expression_based(index: Any) -> bool:
    """True when any element of ``index`` is an expression rather than a plain column."""
    return not all(_is_column(expr) for expr in index.expressions)


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
        if (
            isinstance(value, type)
            and table is not None
            and hasattr(table, "indexes")
            # Skip models re-imported from another module, or each importer would
            # be told about an index it does not own.
            and getattr(value, "__module__", "").startswith(pkg)
        ):
            seen.setdefault(table.name, table)
    return list(seen.values())


_ROUNDTRIP_TARGET = "migrations-roundtrip-pg:"
_DOCS_URL = "https://docs.py.simplemodule.dev/module-authoring"


def expression_index_advice(root: Path | None = None) -> str:
    """How to verify expression indexes, in terms of what this project has.

    The framework repository has a Postgres round-trip make target; an app made
    by ``smpy new`` does not, so pointing it there sends users nowhere (GH #917).
    ``root`` defaults to the working directory, where make, alembic and doctor run.
    """
    makefile = (root or Path.cwd()) / "Makefile"
    try:
        has_target = _ROUNDTRIP_TARGET in makefile.read_text(encoding="utf-8")
    except OSError:
        has_target = False
    if has_target:
        return "verify them on PostgreSQL with `make migrations-roundtrip-pg`"
    return (
        "verify them on PostgreSQL: run `alembic upgrade heads` with `SM_DATABASE_URL` "
        f"pointing at a PostgreSQL database. See {_DOCS_URL}"
    )


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
            suggestion=f"Add them to a revision by hand and {expression_index_advice()}",
        )
    ]


__all__ = [
    "check_expression_indexes_unverifiable",
    "expression_index_advice",
    "find_expression_indexes",
    "index_is_expression_based",
    "module_all_tables",
    "unwrap_ordering",
]
