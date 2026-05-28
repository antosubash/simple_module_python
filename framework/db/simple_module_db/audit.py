"""Audit-record collection: extract change diffs from SQLAlchemy session state.

Pure logic — no DB writes, no module imports. Given a flushing session,
``collect_audit_records`` returns a list of frozen ``AuditRecord`` structs
describing every entity that was created, updated, or deleted.

Two-phase capture
-----------------

Entities whose primary key is assigned by the database (e.g. integer ``id``
columns populated by ``AUTOINCREMENT`` / ``SERIAL``) do not have a usable PK
during ``before_flush`` — it gets populated only when the INSERT executes.
``snapshot_changes`` captures the diff in ``before_flush`` (the only place
SQLAlchemy attribute *history* is still intact) and ``finalize_records``
resolves the now-stable ``entity_id`` in ``after_flush_postexec``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from simple_module_db.mixins import SoftDeleteMixin

# Fields injected by AuditMixin — always excluded from change diffs
# because they are bookkeeping, not business data.
_AUDIT_MIXIN_FIELDS: frozenset[str] = frozenset(
    {"created_at", "updated_at", "created_by", "updated_by"}
)

# Fields injected by SoftDeleteMixin — also excluded because they are
# bookkeeping managed by the soft-delete listener, not business data.
_SOFT_DELETE_MIXIN_FIELDS: frozenset[str] = frozenset({"is_deleted", "deleted_at", "deleted_by"})

_EXCLUDED_MIXIN_FIELDS: frozenset[str] = _AUDIT_MIXIN_FIELDS | _SOFT_DELETE_MIXIN_FIELDS


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Immutable snapshot of a single entity change."""

    entity_type: str
    entity_id: str
    action: str
    changes: list[dict[str, Any]] = field(default_factory=list)
    user_id: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class _PendingChange:
    """Intermediate snapshot — obj_ref preserved so entity_id can be resolved later.

    Produced in ``before_flush`` (when attribute history is still available)
    and consumed in ``after_flush_postexec`` (when DB-assigned PKs are
    populated on the live object).
    """

    obj_ref: object
    entity_type: str
    action: str  # "created" | "updated" | "deleted" | "soft_deleted"
    changes: list[dict[str, Any]]
    user_id: str | None
    correlation_id: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_excluded(obj: object) -> bool:
    """Return True if the model opts out of auditing entirely."""
    return getattr(obj, "__audit_exclude__", False) is True


def _excluded_fields(obj: object) -> set[str]:
    """Return the set of field names that should be skipped for this model."""
    per_model: set[str] = getattr(obj, "__audit_exclude_fields__", set())
    return _EXCLUDED_MIXIN_FIELDS | per_model


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
# Two-phase capture
# ---------------------------------------------------------------------------


def snapshot_changes(
    session: Session,
    user_id: str | None = None,
    correlation_id: str | None = None,
) -> list[_PendingChange]:
    """Phase 1: capture diffs from session state. Called in ``before_flush``.

    Returns intermediate records holding *object references* (not entity_ids)
    because DB-assigned PKs aren't available yet. Attribute *history* is wiped
    after flush, so the diff itself must be captured now.
    """
    pending: list[_PendingChange] = []

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
    for obj in list(session.new):
        if _is_excluded(obj):
            continue

        # Soft-delete listener moves objects from session.deleted → session.new
        # with is_deleted=True.  Classify them as "soft_deleted", not "created".
        if isinstance(obj, SoftDeleteMixin) and getattr(obj, "is_deleted", False):
            pending.append(
                _PendingChange(
                    obj_ref=obj,
                    entity_type=type(obj).__name__,
                    action="soft_deleted",
                    changes=[],
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
            )
            continue

        excl = _get_excluded(obj)
        pk_cols = _get_pk_cols(obj)
        changes: list[dict[str, Any]] = []
        for col_name in _column_names(obj):
            if col_name in excl or col_name in pk_cols:
                continue
            changes.append({"field": col_name, "new": _serialize(getattr(obj, col_name))})
        pending.append(
            _PendingChange(
                obj_ref=obj,
                entity_type=type(obj).__name__,
                action="created",
                changes=changes,
                user_id=user_id,
                correlation_id=correlation_id,
            )
        )

    # ── Updated entities ───────────────────────────────────────────────
    for obj in list(session.dirty):
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
            pending.append(
                _PendingChange(
                    obj_ref=obj,
                    entity_type=type(obj).__name__,
                    action="updated",
                    changes=changes,
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
            )

    # ── Deleted entities ───────────────────────────────────────────────
    for obj in list(session.deleted):
        if _is_excluded(obj):
            continue
        pending.append(
            _PendingChange(
                obj_ref=obj,
                entity_type=type(obj).__name__,
                action="deleted",
                changes=[],
                user_id=user_id,
                correlation_id=correlation_id,
            )
        )

    return pending


def finalize_records(pending: list[_PendingChange]) -> list[AuditRecord]:
    """Phase 2: resolve entity_ids now that DB-assigned PKs are populated.

    Called from ``after_flush_postexec``. By this point the object's primary
    key is stable for new entities (the INSERT has executed).
    """
    return [
        AuditRecord(
            entity_type=p.entity_type,
            entity_id=_entity_pk_str(p.obj_ref),
            action=p.action,
            changes=p.changes,
            user_id=p.user_id,
            correlation_id=p.correlation_id,
        )
        for p in pending
    ]


# ---------------------------------------------------------------------------
# Single-phase public API (used directly by tests / callers with stable PKs)
# ---------------------------------------------------------------------------


def collect_audit_records(
    session: Session,
    user_id: str | None = None,
    correlation_id: str | None = None,
) -> list[AuditRecord]:
    """Inspect session state and return a list of :class:`AuditRecord`.

    Convenience wrapper around :func:`snapshot_changes` +
    :func:`finalize_records` for callers that don't need the two-phase split
    (e.g. tests, or contexts where PKs are already populated client-side).

    Meant to be called from a ``before_flush`` listener *before* the session
    state is cleared. Does not modify the session.
    """
    return finalize_records(snapshot_changes(session, user_id, correlation_id))
