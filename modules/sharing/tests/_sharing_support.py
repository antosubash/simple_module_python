"""A test-only resource type for the sharing tests."""

from __future__ import annotations

import uuid
from collections.abc import Collection
from typing import Any

from sharing.policy import share_exists_for
from simple_module_core.resources import ResourceType, ResourceTypeRegistry
from simple_module_core.user_directory import DirectoryUser
from simple_module_db.resource_policy import OwnedResourcePolicy, select_by_id
from sqlmodel import Field, SQLModel

NOTE_TYPE = "sharing_test.note"
BYPASS = "sharing_test.manage"


class SharingTestNote(SQLModel, table=True):
    __tablename__ = "sharing_test_note"
    __table_args__ = {"extend_existing": True}
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID
    title: str = ""


NOTE_POLICY = OwnedResourcePolicy(
    SharingTestNote.owner_id,
    bypass_perm=BYPASS,
    share_exists=share_exists_for(NOTE_TYPE, SharingTestNote.id),
)


def register_note_type(registry: ResourceTypeRegistry) -> None:
    if NOTE_TYPE not in registry:
        registry.register(
            ResourceType(
                name=NOTE_TYPE, policy=NOTE_POLICY, select_by_id=select_by_id(SharingTestNote)
            )
        )


async def create_note_table(conn: Any) -> None:
    await conn.run_sync(lambda c: SharingTestNote.__table__.create(c, checkfirst=True))


class FakeDirectory:
    """Knows exactly the ids it was given."""

    entity_type = None

    def __init__(self, *ids: str) -> None:
        self.users = {i: DirectoryUser(id=i, email=f"{i[:6]}@example.com") for i in ids}

    async def get_many(
        self, db: Any, ids: Collection[str], *, with_roles: bool = False
    ) -> dict[str, DirectoryUser]:
        return {i: self.users[i] for i in ids if i in self.users}

    async def search(self, db: Any, term: str | None, *, limit: int) -> list[DirectoryUser]:
        return list(self.users.values())[:limit]

    def match_ids(self, term: str) -> Any | None:
        return None

    async def stats(self, db: Any, *, active_window: Any) -> Any:
        return None
