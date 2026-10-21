"""Uploader names come from the user directory, not ``users.models`` (GH #501)."""

from __future__ import annotations

from file_storage.resolve import label_for, resolve_uploader_labels
from simple_module_core.user_directory import DirectoryUser, NullUserDirectory


class _Directory(NullUserDirectory):
    async def get_many(self, db, ids, *, with_roles=False):
        known = {"u1": DirectoryUser(id="u1", email="u1@example.com", full_name="Uma")}
        return {i: known[i] for i in ids if i in known}


async def test_known_uploaders_are_named_and_others_keep_their_id():
    labels = await resolve_uploader_labels(_Directory(), None, ["u1", "gone", None])
    assert labels == {"u1": "Uma"}
    assert label_for("u1", labels) == "Uma"
    assert label_for("gone", labels) == "gone"


async def test_without_a_directory_the_stored_id_is_shown():
    labels = await resolve_uploader_labels(NullUserDirectory(), None, ["u1"])
    assert labels == {}
    assert label_for("u1", labels) == "u1"
