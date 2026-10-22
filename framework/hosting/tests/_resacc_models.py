"""Test-only tables and policy for the resource-access tests (GH #526)."""

from __future__ import annotations

import uuid

from simple_module_core.resources import ACTION_EDIT, ACTION_VIEW, ResourcePrincipal
from simple_module_db.resource_policy import OwnedResourcePolicy
from sqlmodel import Field, SQLModel, exists, select

BYPASS = "resacc.manage"
OWNER = uuid.UUID("00000000-0000-0000-0000-00000000000a")
SHARED = uuid.UUID("00000000-0000-0000-0000-00000000000b")
STRANGER = uuid.UUID("00000000-0000-0000-0000-00000000000c")
EDITOR = uuid.UUID("00000000-0000-0000-0000-00000000000d")


class ResaccDoc(SQLModel, table=True):
    __tablename__ = "resacc_test_doc"
    __table_args__ = {"extend_existing": True}
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID
    visibility: str = "private"
    title: str = ""


class ResaccShare(SQLModel, table=True):
    __tablename__ = "resacc_test_share"
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    doc_id: uuid.UUID
    user_id: str
    role: str = ACTION_VIEW


_ROLES_FOR = {ACTION_VIEW: (ACTION_VIEW, ACTION_EDIT), ACTION_EDIT: (ACTION_EDIT,)}


def share_exists(principal: ResourcePrincipal, action: str):
    roles = _ROLES_FOR.get(action)
    if not roles:
        return None
    return exists(
        select(ResaccShare.id).where(
            ResaccShare.doc_id == ResaccDoc.id,
            ResaccShare.user_id == principal.user_id,
            ResaccShare.role.in_(roles),
        )
    )


POLICY = OwnedResourcePolicy(
    ResaccDoc.owner_id,
    bypass_perm=BYPASS,
    visibility_col=ResaccDoc.visibility,
    share_exists=share_exists,
)


async def seed(session) -> dict[str, ResaccDoc]:
    """Private (shared view to SHARED, edit to EDITOR), public, and another owner's doc."""
    conn = await session.connection()
    for table in (ResaccDoc.__table__, ResaccShare.__table__):
        await conn.run_sync(lambda c, t=table: t.create(c, checkfirst=True))
    docs = {
        "private": ResaccDoc(owner_id=OWNER, title="private"),
        "public": ResaccDoc(owner_id=OWNER, visibility="public", title="public"),
        "other": ResaccDoc(owner_id=STRANGER, title="other"),
    }
    session.add_all(docs.values())
    await session.flush()
    session.add(ResaccShare(doc_id=docs["private"].id, user_id=str(SHARED), role=ACTION_VIEW))
    session.add(ResaccShare(doc_id=docs["private"].id, user_id=str(EDITOR), role=ACTION_EDIT))
    await session.flush()
    return docs


def principal(user: uuid.UUID | None, *perms: str) -> ResourcePrincipal:
    return ResourcePrincipal(user_id=str(user) if user else None, permissions=frozenset(perms))
