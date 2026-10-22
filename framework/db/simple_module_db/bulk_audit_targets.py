"""What a statement writes, by mapped attribute: the input to bulk auditing (#557).

Split from ``bulk_audit``. Only the statement's own ``SET`` / ``VALUES`` targets
count, each resolved to the model attribute it writes, so a stray key in the
execute params, or an excluded column named by its Core key, cannot slip into
an audit row's ``changes``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import ORMExecuteState
from sqlalchemy.sql.elements import BindParameter, ClauseElement, False_
from sqlalchemy.sql.visitors import iterate

from simple_module_db.audit import _serialize


def _attr_names(cls: type) -> dict[str, str]:
    """Column key and name → mapped attribute key, for every column attribute."""
    names: dict[str, str] = {}
    for prop in sa_inspect(cls).column_attrs:
        for col in prop.columns:
            names.setdefault(str(getattr(col, "key", "")), prop.key)
            names.setdefault(str(getattr(col, "name", "")), prop.key)
    return names


def _attr(key: Any, names: dict[str, str]) -> str | None:
    """The attribute a ``SET`` / ``VALUES`` target writes, or ``None`` if unmapped."""
    raw = key if isinstance(key, str) else getattr(key, "key", None) or getattr(key, "name", None)
    return names.get(str(raw)) if raw is not None else None


def _resolve(value: Any, params: Any) -> Any:
    """A bound value through the execute params; other SQL stays an expression."""
    if isinstance(value, BindParameter):
        if isinstance(params, dict) and value.key in params:
            return params[value.key]
        return value.effective_value
    return value


def _shown(value: Any) -> Any:
    return str(value) if isinstance(value, ClauseElement) else _serialize(value)


def _targets(execute_state: ORMExecuteState, cls: type) -> tuple[dict[str, list[Any]], bool]:
    """Attribute → every value the statement writes to it, and whether it is many rows.

    Every key is resolved to the mapped attribute it writes, and only mapped
    columns count, so a stray param key never reaches ``changes`` and an
    excluded column is excluded under its Core key too. A param whose key names
    a column and is not one of the statement's own bind parameters is a
    ``SET`` target exactly as SQLAlchemy reads it (it does get written), so it
    is a target here as well; ignoring it would let a write hide behind an
    excluded ``.values()`` entry.
    """
    names = _attr_names(cls)
    stmt, params = execute_state.statement, execute_state.parameters
    multi = getattr(stmt, "_multi_values", None)
    pairs = getattr(stmt, "_ordered_values", None) or list(
        (getattr(stmt, "_values", None) or {}).items()
    )
    if isinstance(params, list):
        rows, many = params, True
    elif multi:
        rows, many = [r for r in multi[0] if isinstance(r, dict)], True
    else:
        row = {k: _resolve(v, params) for k, v in pairs}
        if isinstance(params, dict):
            tree = stmt if isinstance(stmt, ClauseElement) else None
            bound = {e.key for e in iterate(tree) if isinstance(e, BindParameter)}
            row.update({k: v for k, v in params.items() if k not in bound})
        rows, many = [row], False
    targets: dict[str, list[Any]] = {}
    for row in rows:
        for key, value in row.items():
            attr = _attr(key, names)
            if attr is not None:
                targets.setdefault(attr, []).append(value)
    return targets, many


def _is_set(value: Any) -> bool:
    """Whether a written ``is_deleted`` value trashes the row (unknown SQL counts)."""
    if isinstance(value, False_):
        return False
    return True if isinstance(value, ClauseElement) else bool(value)
