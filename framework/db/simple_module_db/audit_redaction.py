"""Shared credential redaction for flush, statement and manual audit capture."""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import inspect

AUDIT_REDACTED: Final = "[redacted]"


def model_for_audit(model: type | str) -> type | None:
    """Accept a mapped class or its registered class name; None for unknown names."""
    if isinstance(model, type):
        return model
    from simple_module_db.model_registry import classes_by_table

    return next((cls for cls in classes_by_table.values() if cls.__name__ == model), None)


def redact_changes(
    model: type, changes: list[dict[str, Any]], obj: object | None = None
) -> list[dict[str, Any]]:
    """Keep fields and diff shape, replacing credential values before delivery.

    A row predicate receives both the current and pre-edit column values. With
    no row (statement/manual capture) it receives None and must fail closed.
    """
    if not changes:
        return changes
    fields = set(getattr(model, "__audit_redact_fields__", ()))
    predicate = getattr(model, "__audit_redact_row__", None)
    if predicate is not None:
        if obj is None:
            fields.update(predicate(None))
        else:
            state = inspect(obj)
            current: dict[str, Any] = {}
            previous: dict[str, Any] = {}
            for attr in state.mapper.column_attrs:
                key = attr.key
                value = current[key] = state.dict.get(key)
                history = state.attrs[key].history
                if history.has_changes():
                    previous[key] = history.deleted[0] if history.deleted else None
                else:
                    previous[key] = value
            fields.update(predicate(current))
            if state.persistent:
                fields.update(predicate(previous))
    if not fields:
        return changes
    return [
        {
            k: AUDIT_REDACTED if c["field"] in fields and k in {"old", "new"} else v
            for k, v in c.items()
        }
        for c in changes
    ]


def pk_is_redacted(model: type | None) -> bool:
    """True when a primary-key column of ``model`` is itself a redacted credential."""
    fields = getattr(model, "__audit_redact_fields__", None)
    if model is None or not fields:
        return False
    return any(col.key in fields for col in inspect(model).primary_key)


def redact_entity_id(model: type | None, entity_id: str) -> str:
    return AUDIT_REDACTED if pk_is_redacted(model) else entity_id
