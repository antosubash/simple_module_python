"""Subject validation must happen even when callers bypass the picker (#991)."""

import uuid
from unittest.mock import AsyncMock

import pytest
from _sharing_support import NOTE_TYPE, FakeDirectory, SharingTestNote, register_note_type
from pydantic import ValidationError
from sharing.contracts.schemas import ShareGrant
from sharing.core.service import SharingError, SharingService
from sharing.models import ResourceShare
from simple_module_core.resources import ResourcePrincipal, ResourceTypeRegistry
from simple_module_core.user_directory import DirectoryUser
from sqlalchemy.orm import make_transient_to_detached


@pytest.mark.parametrize("subject_type", ["group", "tenant", ""])
def test_subject_type_is_validated(subject_type):
    with pytest.raises(ValidationError):
        ShareGrant.model_validate(
            {
                "resource_type": NOTE_TYPE,
                "resource_id": "note",
                "subject_id": "friend",
                "subject_type": subject_type,
            }
        )


async def test_service_refuses_disabled_user_before_writing():
    registry = ResourceTypeRegistry()
    register_note_type(registry)
    directory = FakeDirectory("friend")
    directory.users["friend"] = DirectoryUser(id="friend", email="f@test", is_active=False)
    db = AsyncMock()
    service = SharingService(db, registry, directory)
    note = SharingTestNote(owner_id=uuid.uuid4())
    make_transient_to_detached(note)
    service._authorize = AsyncMock(return_value=note)
    service._existing = AsyncMock(
        return_value=ResourceShare(
            resource_type=NOTE_TYPE,
            resource_id=note.id.hex,
            subject_id="friend",
            granted_by="owner",
        )
    )
    with pytest.raises(SharingError) as error:
        await service.grant(
            ResourcePrincipal("owner"),
            ShareGrant(resource_type=NOTE_TYPE, resource_id="note", subject_id="friend"),
        )
    assert error.value.status_code == 422
    db.flush.assert_not_awaited()
