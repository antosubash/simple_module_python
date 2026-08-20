"""The grant-search must treat LIKE metacharacters as literal text."""

from __future__ import annotations

from permissions.constants import PERM_MANAGE, PERM_VIEW, PERMISSION_GROUP
from permissions.service import PermissionService
from simple_module_core.permissions import PermissionRegistry
from test_permissions_module import _seed_user


class TestGrantSearchEscaping:
    async def test_search_matches_like_metacharacters_literally(self, db_session):
        """A literal "_" in the search term must match as text, not act as the
        single-character SQL wildcard — the same contract the users,
        background_tasks and file_storage searches follow."""
        await _seed_user(db_session, email="dana_x@test")
        await _seed_user(db_session, email="danaYx@test")
        registry = PermissionRegistry()
        registry.add_group(PERMISSION_GROUP, [PERM_VIEW, PERM_MANAGE])
        svc = PermissionService(db_session, registry)

        rows = await svc.list_users_with_counts(search="dana_x")

        assert [u.email for u, _count in rows] == ["dana_x@test"]
