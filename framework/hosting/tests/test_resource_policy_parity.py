"""``can`` and ``filter`` agree on case-variant owner ids (GH #526 review).

A detail check that admits a row the list hides (or the reverse) is an
authorisation differential, so both sides must compare the same way.
"""

from __future__ import annotations

import uuid

import pytest
from _resacc_models import ResaccDoc
from simple_module_core.resources import ACTION_EDIT, ResourcePrincipal
from simple_module_db.resource_policy import OwnedResourcePolicy
from sqlmodel import Field, SQLModel, select


class ResaccNote(SQLModel, table=True):
    __tablename__ = "resacc_test_note"
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    owner: str


STR_POLICY = OwnedResourcePolicy(ResaccNote.owner, bypass_perm=None)
UUID_POLICY = OwnedResourcePolicy(ResaccDoc.owner_id, bypass_perm=None)


async def _visible(session, policy, who, model) -> bool:
    stmt = policy.filter(who, ACTION_EDIT, select(model))
    return (await session.execute(stmt)).scalars().first() is not None


@pytest.mark.parametrize("asker", ["Alice", "alice", "ALICE"])
async def test_string_owner_case_variants_agree(db_session, asker):
    conn = await db_session.connection()
    await conn.run_sync(lambda c: ResaccNote.__table__.create(c, checkfirst=True))
    note = ResaccNote(owner="Alice")
    db_session.add(note)
    await db_session.flush()
    who = ResourcePrincipal(user_id=asker)
    in_sql = await _visible(db_session, STR_POLICY, who, ResaccNote)
    assert STR_POLICY.can(who, ACTION_EDIT, note) is in_sql
    assert in_sql is (asker == "Alice")


@pytest.mark.parametrize("upper", [False, True])
async def test_uuid_owner_case_variants_agree(db_session, upper):
    conn = await db_session.connection()
    await conn.run_sync(lambda c: ResaccDoc.__table__.create(c, checkfirst=True))
    owner = uuid.UUID("00000000-0000-0000-0000-0000000000ff")
    doc = ResaccDoc(owner_id=owner)
    db_session.add(doc)
    await db_session.flush()
    who = ResourcePrincipal(user_id=str(owner).upper() if upper else str(owner))
    assert await _visible(db_session, UUID_POLICY, who, ResaccDoc)
    assert UUID_POLICY.can(who, ACTION_EDIT, doc)


async def test_malformed_id_owns_nothing_on_uuid_column(db_session):
    conn = await db_session.connection()
    await conn.run_sync(lambda c: ResaccDoc.__table__.create(c, checkfirst=True))
    doc = ResaccDoc(owner_id=uuid.uuid4())
    db_session.add(doc)
    await db_session.flush()
    who = ResourcePrincipal(user_id="not-a-uuid")
    assert not await _visible(db_session, UUID_POLICY, who, ResaccDoc)
    assert not UUID_POLICY.can(who, ACTION_EDIT, doc)
