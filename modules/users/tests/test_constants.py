"""Tests for stable UUID constants in the users module."""

from __future__ import annotations


class TestConstants:
    def test_admin_role_id_is_stable(self):
        from users.constants import ADMIN_ROLE_ID

        assert str(ADMIN_ROLE_ID) == "00000000-0000-0000-0000-000000000001"

    def test_user_role_id_is_stable(self):
        from users.constants import USER_ROLE_ID

        assert str(USER_ROLE_ID) == "00000000-0000-0000-0000-000000000002"

    def test_admin_uuid_hex(self):
        from users.constants import ADMIN_ROLE_ID

        assert ADMIN_ROLE_ID.hex == "00000000000000000000000000000001"

    def test_user_uuid_hex(self):
        from users.constants import USER_ROLE_ID

        assert USER_ROLE_ID.hex == "00000000000000000000000000000002"

    def test_ids_differ(self):
        from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID

        assert ADMIN_ROLE_ID != USER_ROLE_ID
