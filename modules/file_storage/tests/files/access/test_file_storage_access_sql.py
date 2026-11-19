"""Real SQLite policy queries without the app/async-driver fixtures (#999)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from file_storage.core.constants import Permission
from file_storage.files.access import FileAccess
from file_storage.models import StoredFile
from simple_module_core.file_access import (
    ACTION_PUBLISH,
    FileAccessPolicyRegistry,
    register_file_access_policy,
)
from simple_module_core.resources import ACTION_DELETE, ACTION_EDIT, ACTION_VIEW, ResourcePrincipal
from simple_module_db.resource_policy import OwnedResourcePolicy
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

OWNER = "owner"
OTHER = "other"
REVIEW = "guides.review"
TAG = "guides.licence"


@pytest.fixture
def rows():
    engine = create_engine("sqlite://")
    StoredFile.__table__.create(engine)
    with Session(engine) as db:
        for name, tag, public in [
            ("private", TAG, False),
            ("old-public", TAG, True),
            ("legacy", None, True),
            ("unregistered", "missing", True),
        ]:
            db.add(
                StoredFile(
                    id=uuid.uuid4(),
                    tenant_id="tenant",
                    created_by=OWNER,
                    key=name,
                    filename=name,
                    content_type="application/pdf",
                    size_bytes=7,
                    backend="filesystem",
                    owner_module=tag,
                    public=public,
                )
            )
        db.commit()
        yield db
    engine.dispose()


def access(user, permissions=(), *, publishable=False, public=False):
    registry = FileAccessPolicyRegistry()
    registry.register(
        TAG,
        OwnedResourcePolicy(StoredFile.created_by, bypass_perm=REVIEW),
        publishable=publishable,
    )
    return FileAccess(registry, ResourcePrincipal(user, frozenset(permissions)), public=public)


def names(db, policy, action=ACTION_VIEW):
    return sorted(db.scalars(policy.apply(select(StoredFile.filename), action)).all())


def test_tagged_access_adds_reviewers_and_does_not_trust_managers(rows):
    assert names(rows, access(OWNER)) == ["legacy", "old-public", "private"]
    assert names(rows, access(OTHER, [REVIEW])) == ["old-public", "private"]
    assert names(rows, access(OTHER, [Permission.MANAGE])) == ["legacy"]
    assert names(rows, access(OTHER)) == []


def test_never_publishable_and_missing_tags_fail_closed(rows):
    assert names(rows, access(OWNER), ACTION_PUBLISH) == ["legacy"]
    assert names(rows, access(None, public=True)) == ["legacy"]
    assert names(rows, access(OWNER), ACTION_EDIT) == ["legacy", "old-public", "private"]


def test_filter_applies_before_count_and_pagination(rows):
    policy = access(OTHER, [REVIEW])
    count = rows.scalar(policy.apply(select(func.count(StoredFile.id))))
    page = rows.scalars(
        policy.apply(select(StoredFile.filename)).order_by(StoredFile.filename).limit(1)
    )
    assert count == 2
    assert list(page) == ["old-public"]


def test_publishable_policy_and_legacy_delete(rows):
    assert names(rows, access(OWNER, publishable=True), ACTION_PUBLISH) == [
        "legacy",
        "old-public",
        "private",
    ]
    assert names(rows, access(OTHER, [Permission.MANAGE]), ACTION_DELETE) == ["legacy"]


def test_sql_policy_can_use_exists_even_when_can_is_false(rows):
    class SqlOnly:
        def filter(self, principal, action, stmt):
            return (
                stmt.where(StoredFile.filename == "private")
                if action == ACTION_VIEW
                else stmt.where(False)
            )

        def can(self, principal, action, obj):
            return False

    registry = FileAccessPolicyRegistry()
    registry.register(TAG, SqlOnly())
    policy = FileAccess(registry, ResourcePrincipal(OTHER))
    assert names(rows, policy) == ["private"]
    assert names(rows, policy, ACTION_DELETE) == []


def test_registration_is_per_app_and_rejects_duplicates():
    first = SimpleNamespace(state=SimpleNamespace())
    second = SimpleNamespace(state=SimpleNamespace())
    policy = OwnedResourcePolicy(StoredFile.created_by, bypass_perm=REVIEW)
    register_file_access_policy(first, TAG, policy)
    register_file_access_policy(second, TAG, policy)
    with pytest.raises(ValueError, match="twice"):
        register_file_access_policy(first, TAG, policy)
    for tag in ("", "x" * 129, "Guides", "guides/licence"):
        with pytest.raises(ValueError):
            register_file_access_policy(first, tag, policy)
