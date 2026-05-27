"""Audit-record collection: extract change diffs from SQLAlchemy session state.

Pure logic — no DB writes, no module imports. Given a flushing session,
``collect_audit_records`` returns a list of frozen ``AuditRecord`` structs
describing every entity that was created, updated, or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

# Fields injected by AuditMixin — always excluded from change diffs
# because they are bookkeeping, not business data.
_AUDIT_MIXIN_FIELDS: frozenset[str] = frozenset(
    {"created_at", "updated_at", "created_by", "updated_by"}
)


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Immutable snapshot of a single entity change."""

    entity_type: str
    entity_id: str
    action: str
    changes: list[dict[str, Any]] = field(default_factory=list)
    user_id: str | None = None
    correlation_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_excluded(obj: object) -> bool:
    """Return True if the model opts out of auditing entirely."""
    return getattr(obj, "__audit_exclude__", False) is True


def _excluded_fields(obj: object) -> set[str]:
    """Return the set of field names that should be skipped for this model."""
    per_model: set[str] = getattr(obj, "__audit_exclude_fields__", set())
    return _AUDIT_MIXIN_FIELDS | per_model


def _entity_pk_str(obj: object) -> str:
    """Return the primary-key value(s) as a string."""
    inspector = sa_inspect(obj)
    identity = inspector.identity
    if identity is None:
        # Pre-flush: fall back to the mapper-level key attrs
        mapper = inspector.mapper
        vals = tuple(getattr(obj, col.key) for col in mapper.primary_key)
        if len(vals) == 1:
            return str(vals[0]) if vals[0] is not None else ""
        return str(vals)
    if len(identity) == 1:
        return str(identity[0])
    return str(identity)


def _column_names(obj: object) -> list[str]:
    """Return all mapped column attribute names for *obj*."""
    mapper = sa_inspect(type(obj))
    return [col.key for col in mapper.column_attrs]


def _serialize(value: Any) -> Any:
    """Normalize a column value for JSON-safe storage."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Core collection
# ---------------------------------------------------------------------------


def collect_audit_records(
    session: Session,
    user_id: str | None = None,
    correlation_id: str | None = None,
) -> list[AuditRecord]:
    """Inspect session state and return a list of :class:`AuditRecord`.

    Meant to be called from a ``before_flush`` listener *before* the session
    state is cleared.  Does not modify the session.
    """
    records: list[AuditRecord] = []

    excluded_cache: dict[type, set[str]] = {}
    pk_cols_cache: dict[type, set[str]] = {}

    def _get_excluded(obj: object) -> set[str]:
        cls = type(obj)
        if cls not in excluded_cache:
            excluded_cache[cls] = _excluded_fields(obj)
        return excluded_cache[cls]

    def _get_pk_cols(obj: object) -> set[str]:
        cls = type(obj)
        if cls not in pk_cols_cache:
            mapper = sa_inspect(cls)
            pk_cols_cache[cls] = {col.key for col in mapper.primary_key}
        return pk_cols_cache[cls]

    # ── Created entities ───────────────────────────────────────────────
    for obj in session.new:
        if _is_excluded(obj):
            continue
        excl = _get_excluded(obj)
        pk_cols = _get_pk_cols(obj)
        changes: list[dict[str, Any]] = []
        for col_name in _column_names(obj):
            if col_name in excl or col_name in pk_cols:
                continue
            changes.append({"field": col_name, "new": _serialize(getattr(obj, col_name))})
        records.append(
            AuditRecord(
                entity_type=type(obj).__name__,
                entity_id=_entity_pk_str(obj),
                action="created",
                changes=changes,
                user_id=user_id,
                correlation_id=correlation_id,
            )
        )

    # ── Updated entities ───────────────────────────────────────────────
    for obj in session.dirty:
        if not session.is_modified(obj):
            continue
        if _is_excluded(obj):
            continue
        excl = _get_excluded(obj)
        pk_cols = _get_pk_cols(obj)
        inspector = sa_inspect(obj)
        changes = []
        for col_name in _column_names(obj):
            if col_name in excl or col_name in pk_cols:
                continue
            hist = inspector.attrs[col_name].history
            if not hist.has_changes():
                continue
            old_val = hist.deleted[0] if hist.deleted else None
            new_val = hist.added[0] if hist.added else None
            changes.append(
                {"field": col_name, "old": _serialize(old_val), "new": _serialize(new_val)}
            )
        if changes:
            records.append(
                AuditRecord(
                    entity_type=type(obj).__name__,
                    entity_id=_entity_pk_str(obj),
                    action="updated",
                    changes=changes,
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
            )

    # ── Deleted entities ───────────────────────────────────────────────
    for obj in session.deleted:
        if _is_excluded(obj):
            continue
        records.append(
            AuditRecord(
                entity_type=type(obj).__name__,
                entity_id=_entity_pk_str(obj),
                action="deleted",
                changes=[],
                user_id=user_id,
                correlation_id=correlation_id,
            )
        )

    return records
