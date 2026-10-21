"""The core user-directory protocol, its null object and the shared helpers (GH #501)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from simple_module_core.activity_feed import (
    ActivityFeed,
    ActivityItem,
    get_activity_feed,
    set_activity_feed,
)
from simple_module_core.user_directory import (
    GET_MANY_CHUNK,
    DirectoryStats,
    DirectoryUser,
    NullUserDirectory,
    UserDirectory,
    chunked,
    get_user_directory,
    parse_user_ids,
    resolve_user_labels,
    set_user_directory,
)


def _app() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace())


class _FakeDirectory:
    entity_type: str | None = "User"

    def __init__(self, users: list[DirectoryUser]) -> None:
        self.users = {u.id: u for u in users}
        self.calls: list[set[str]] = []

    async def get_many(self, db, ids, *, with_roles=False):
        self.calls.append(set(ids))
        return {i: self.users[i] for i in ids if i in self.users}

    async def search(self, db, term, *, limit):
        return list(self.users.values())[:limit]

    def match_ids(self, term):
        return None

    async def stats(self, db, *, active_window):
        return DirectoryStats(total=len(self.users), active_since=None, created_this_month=None)


class TestDirectoryUser:
    def test_label_prefers_the_full_name(self):
        assert DirectoryUser(id="1", email="a@x", full_name="Ada").label == "Ada"

    def test_label_falls_back_to_the_email(self):
        assert DirectoryUser(id="1", email="a@x").label == "a@x"
        assert DirectoryUser(id="1", email="a@x", full_name="").label == "a@x"

    def test_roles_default_to_unknown_not_none_held(self):
        assert DirectoryUser(id="1", email="a@x").roles is None


class TestNullUserDirectory:
    async def test_knows_nobody(self):
        d = NullUserDirectory()
        assert d.entity_type is None
        assert await d.get_many(None, [str(uuid.uuid4())], with_roles=True) == {}
        assert await d.search(None, "ada", limit=10) == []
        assert d.match_ids("ada") is None

    async def test_stats_are_unknown_not_zero(self):
        stats = await NullUserDirectory().stats(None, active_window=timedelta(days=7))
        assert stats == DirectoryStats(total=None, active_since=None, created_this_month=None)

    def test_satisfies_the_protocol(self):
        assert isinstance(NullUserDirectory(), UserDirectory)


class TestRegistration:
    def test_without_a_provider_the_null_directory_answers(self):
        assert isinstance(get_user_directory(_app()), NullUserDirectory)

    def test_the_registered_directory_wins(self):
        app = _app()
        directory = _FakeDirectory([])
        set_user_directory(app, directory)
        assert get_user_directory(app) is directory


class TestHelpers:
    def test_parse_keeps_the_callers_spelling(self):
        uid = uuid.uuid4()
        upper = str(uid).upper()
        assert parse_user_ids([upper, "celery-worker", "", "svc:1"]) == {uid: [upper]}

    def test_parse_keeps_every_spelling_of_one_id(self):
        uid = uuid.uuid4()
        spellings = [str(uid), str(uid).upper(), uid.hex, f"{{{uid}}}", str(uid)]
        assert parse_user_ids(spellings) == {uid: spellings[:4]}

    def test_parse_tolerates_non_strings(self):
        assert parse_user_ids([None, 3]) == {}

    def test_chunked_bounds_every_slice(self):
        items = list(range(GET_MANY_CHUNK * 2 + 1))
        slices = list(chunked(items))
        assert [len(s) for s in slices] == [GET_MANY_CHUNK, GET_MANY_CHUNK, 1]
        assert [x for s in slices for x in s] == items

    async def test_resolve_labels_uses_the_one_naming_rule(self):
        directory = _FakeDirectory(
            [DirectoryUser(id="a", email="a@x", full_name="Ada"), DirectoryUser("b", "b@x")]
        )
        labels = await resolve_user_labels(directory, None, ["a", "b", "gone", "", "a"])
        assert labels == {"a": "Ada", "b": "b@x"}
        assert directory.calls == [{"a", "b", "gone"}]

    async def test_resolve_labels_short_circuits_without_ids(self):
        directory = _FakeDirectory([])
        assert await resolve_user_labels(directory, None, ["", ""]) == {}
        assert directory.calls == []


class _Feed:
    async def recent_for_actor(self, db, actor_id, *, limit, permissions):
        return [ActivityItem(datetime.now(UTC), "created", "Setting", "k")]


class TestActivityFeed:
    def test_absent_until_something_records_activity(self):
        assert get_activity_feed(_app()) is None

    def test_set_and_remove(self):
        app = _app()
        feed = _Feed()
        set_activity_feed(app, feed)
        assert get_activity_feed(app) is feed
        assert isinstance(feed, ActivityFeed)
        set_activity_feed(app, None)
        assert get_activity_feed(app) is None

    def test_item_label_and_changes_are_optional(self):
        item = ActivityItem(datetime.now(UTC), "updated", "User", "1")
        assert item.entity_label is None
        assert item.changes is None
