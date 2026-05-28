"""Tests for AuditRecord dataclass and collect_audit_records diff collection.

Verifies the pure-logic core: given SQLAlchemy session state, produce a list
of ``AuditRecord`` structs describing what changed.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import FrozenInstanceError
from typing import ClassVar

import pytest
from simple_module_db.audit import (
    AuditRecord,
    collect_audit_records,
    finalize_records,
    snapshot_changes,
)
from simple_module_db.base import create_module_base
from simple_module_db.listeners import register_listeners
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from simple_module_db.provider import DatabaseProvider
from simple_module_db.session import init_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field

_AuditBase = create_module_base("test_audit", provider=DatabaseProvider.SQLITE)


class AuditTestItem(_AuditBase, AuditMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Standard audited entity for testing."""

    __tablename__ = "test_audit_item"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    value: int = Field(default=0)


class ExcludedModel(_AuditBase, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Model that opts out of auditing entirely."""

    __tablename__ = "test_audit_excluded"
    __audit_exclude__ = True
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


class PartialExcludeModel(_AuditBase, AuditMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Model with specific fields excluded from audit tracking."""

    __tablename__ = "test_audit_partial"
    __audit_exclude_fields__: ClassVar[set[str]] = {"password_hash"}
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(max_length=100)
    password_hash: str = Field(max_length=255, default="")


class SoftDeleteItem(_AuditBase, AuditMixin, SoftDeleteMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Audited entity with soft-delete support for testing."""

    __tablename__ = "test_audit_soft_delete_item"
    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=100)


class IntPKItem(_AuditBase, AuditMixin, table=True):  # type: ignore[call-arg]  # ty: ignore[unsupported-base]
    """Entity with a DB-assigned integer primary key (BUG-002 regression case)."""

    __tablename__ = "test_audit_int_pk_item"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)


@pytest.fixture
async def audit_session() -> AsyncGenerator[AsyncSession, None]:
    """Session backed by in-memory SQLite with listeners registered."""
    db_state = init_db("sqlite+aiosqlite:///:memory:")
    try:
        register_listeners(db_state)
        async with db_state.engine.begin() as conn:
            await conn.run_sync(_AuditBase.metadata.create_all)
        async with db_state.session_factory() as session:
            yield session
    finally:
        await db_state.engine.dispose()


# ── AuditRecord dataclass ─────────────────────────────────────────────────


def test_audit_record_is_frozen():
    record = AuditRecord(
        entity_type="Item",
        entity_id="1",
        action="created",
        changes=[{"field": "name", "new": "test"}],
        user_id="alice",
        correlation_id="req-123",
    )
    with pytest.raises(FrozenInstanceError):
        record.action = "updated"  # type: ignore[misc]


# ── collect_audit_records: created ─────────────────────────────────────────


async def test_collect_records_for_new_entity(audit_session: AsyncSession):
    item = AuditTestItem(name="widget", value=42)
    audit_session.add(item)

    # Collect before flush (inside the sync session via run_sync)
    records: list[AuditRecord] = []

    def _collect(session):
        records.extend(collect_audit_records(session, user_id="alice", correlation_id="req-1"))

    await audit_session.run_sync(_collect)

    assert len(records) == 1
    rec = records[0]
    assert rec.entity_type == "AuditTestItem"
    assert rec.action == "created"
    assert rec.user_id == "alice"
    assert rec.correlation_id == "req-1"

    # Should contain name and value, but not PK or AuditMixin fields
    field_names = {c["field"] for c in rec.changes}
    assert "name" in field_names
    assert "value" in field_names
    assert "id" not in field_names
    assert "created_at" not in field_names
    assert "updated_at" not in field_names

    # Check values
    name_change = next(c for c in rec.changes if c["field"] == "name")
    assert name_change["new"] == "widget"
    value_change = next(c for c in rec.changes if c["field"] == "value")
    assert value_change["new"] == 42


# ── collect_audit_records: excluded model ──────────────────────────────────


async def test_excluded_model_produces_no_records(audit_session: AsyncSession):
    excluded = ExcludedModel(name="secret")
    audit_session.add(excluded)

    records: list[AuditRecord] = []

    def _collect(session):
        records.extend(collect_audit_records(session))

    await audit_session.run_sync(_collect)

    assert len(records) == 0


# ── collect_audit_records: excluded fields ─────────────────────────────────


async def test_excluded_fields_are_omitted(audit_session: AsyncSession):
    user = PartialExcludeModel(username="bob", password_hash="s3cret")
    audit_session.add(user)

    records: list[AuditRecord] = []

    def _collect(session):
        records.extend(collect_audit_records(session))

    await audit_session.run_sync(_collect)

    assert len(records) == 1
    field_names = {c["field"] for c in records[0].changes}
    assert "username" in field_names
    assert "password_hash" not in field_names


# ── collect_audit_records: AuditMixin fields always excluded ───────────────


async def test_audit_mixin_fields_excluded_by_default(audit_session: AsyncSession):
    item = AuditTestItem(name="audited", value=1)
    audit_session.add(item)

    records: list[AuditRecord] = []

    def _collect(session):
        records.extend(collect_audit_records(session))

    await audit_session.run_sync(_collect)

    assert len(records) == 1
    field_names = {c["field"] for c in records[0].changes}
    for mixin_field in ("created_at", "updated_at", "created_by", "updated_by"):
        assert mixin_field not in field_names, f"{mixin_field} should be excluded"


# ── collect_audit_records: updated ─────────────────────────────────────────


async def test_collect_records_for_update(audit_session: AsyncSession):
    # First create and commit so the entity is persistent
    item = AuditTestItem(name="original", value=10)
    audit_session.add(item)
    await audit_session.commit()
    await audit_session.refresh(item)

    # Now modify it
    item.name = "renamed"

    records: list[AuditRecord] = []

    def _collect(session):
        records.extend(collect_audit_records(session, user_id="bob", correlation_id="req-2"))

    await audit_session.run_sync(_collect)

    assert len(records) == 1
    rec = records[0]
    assert rec.entity_type == "AuditTestItem"
    assert rec.action == "updated"
    assert rec.entity_id == str(item.id)
    assert rec.user_id == "bob"

    # Should only contain the changed field
    assert len(rec.changes) == 1
    change = rec.changes[0]
    assert change["field"] == "name"
    assert change["old"] == "original"
    assert change["new"] == "renamed"


# ── collect_audit_records: soft-deleted entity ────────────────────────────


async def test_soft_deleted_entity_produces_soft_deleted_record(
    audit_session: AsyncSession,
):
    """A SoftDeleteMixin object re-added to session.new with is_deleted=True
    should produce action='soft_deleted', not action='created'."""
    item = SoftDeleteItem(title="doomed")
    audit_session.add(item)
    await audit_session.commit()
    await audit_session.refresh(item)

    # Simulate what the soft-delete listener does: expunge from deleted,
    # set is_deleted=True, re-add to session.new.  We use make_transient
    # so SQLAlchemy treats the re-added object as new (matching the
    # session state that triggers Bug 1).
    await audit_session.delete(item)

    def _simulate_soft_delete(session):
        from sqlalchemy.orm import make_transient

        session.expunge(item)
        item.is_deleted = True
        make_transient(item)
        session.add(item)

    await audit_session.run_sync(_simulate_soft_delete)

    records: list[AuditRecord] = []

    def _collect(session):
        records.extend(collect_audit_records(session, user_id="admin", correlation_id="req-sd"))

    await audit_session.run_sync(_collect)

    assert len(records) == 1
    rec = records[0]
    assert rec.action == "soft_deleted"
    assert rec.entity_type == "SoftDeleteItem"
    assert rec.entity_id == str(item.id)
    assert rec.changes == []
    assert rec.user_id == "admin"
    assert rec.correlation_id == "req-sd"


# ── collect_audit_records: soft-delete fields excluded from diffs ─────────


async def test_soft_delete_fields_excluded(audit_session: AsyncSession):
    """is_deleted, deleted_at, deleted_by should never appear in changes."""
    item = SoftDeleteItem(title="widget")
    audit_session.add(item)

    records: list[AuditRecord] = []

    def _collect(session):
        records.extend(collect_audit_records(session))

    await audit_session.run_sync(_collect)

    assert len(records) == 1
    field_names = {c["field"] for c in records[0].changes}
    assert "title" in field_names
    for soft_field in ("is_deleted", "deleted_at", "deleted_by"):
        assert soft_field not in field_names, f"{soft_field} should be excluded"


# ── Two-phase capture: DB-assigned integer PKs (BUG-002) ──────────────────


async def test_created_entry_has_resolved_int_pk(audit_session: AsyncSession):
    """Integer PKs are populated by the DB during INSERT, so entity_id should
    be resolved correctly in the audit log via the two-phase capture.

    Regression test for BUG-002: single-phase ``collect_audit_records`` ran
    in ``before_flush`` where the PK was still ``None``, yielding
    ``entity_id=""``. The two-phase flow snapshots the diff up-front but
    defers ``entity_id`` resolution until after the flush has assigned it.
    """
    item = IntPKItem(name="hello")
    audit_session.add(item)

    # Phase 1: snapshot while id is still None (pre-flush).
    pending_holder: list = []

    def _phase1(session):
        pending_holder.extend(snapshot_changes(session, None, None))

    await audit_session.run_sync(_phase1)
    assert any(p.entity_type == "IntPKItem" for p in pending_holder)
    assert item.id is None  # PK not yet assigned

    # Now flush to assign the PK
    await audit_session.flush()
    assert item.id is not None  # DB assigned it

    # Phase 2: finalize — entity_id should now be the real PK
    records = finalize_records(pending_holder)
    int_records = [r for r in records if r.entity_type == "IntPKItem"]
    assert len(int_records) == 1
    assert int_records[0].entity_id == str(item.id)
    assert int_records[0].entity_id != ""
