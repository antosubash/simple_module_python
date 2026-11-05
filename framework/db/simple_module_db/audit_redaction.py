"""Shared credential redaction for flush, statement and manual audit capture."""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import inspect

AUDIT_REDACTED: Final = "[redacted]"


def model_for_audit(model: type | str) -> type | None:
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
    fields = set(getattr(model, "__audit_redact_fields__", ()))
    predicate = getattr(model, "__audit_redact_row__", None)
    if predicate is not None:
        if obj is None:
            fields.update(predicate(None))
        else:
            state = inspect(obj)
            current = {attr.key: state.dict.get(attr.key) for attr in state.mapper.column_attrs}
            previous = dict(current)
            for attr in state.mapper.column_attrs:
                history = state.attrs[attr.key].history
                if history.has_changes():
                    previous[attr.key] = history.deleted[0] if history.deleted else None
            fields.update(predicate(current))
            if state.persistent:
                fields.update(predicate(previous))
    return [
        {
            k: AUDIT_REDACTED if c["field"] in fields and k in {"old", "new"} else v
            for k, v in c.items()
        }
        for c in changes
    ]


def redact_entity_id(model: type | None, entity_id: str) -> str:
    if model is not None:
        fields = getattr(model, "__audit_redact_fields__", ())
        if any(col.key in fields for col in inspect(model).primary_key):
            return AUDIT_REDACTED
    return entity_id
