"""Tests for the UserContext value object (construction, roles, tenant)."""

from __future__ import annotations

from auth.contracts.schemas import UserContext


class TestUserContextFromUser:
    async def test_from_user_basic(self):
        """from_user correctly maps id, email, name, roles, and tenant_id."""
        import uuid
        from types import SimpleNamespace

        role_a = SimpleNamespace(name="admin")
        role_b = SimpleNamespace(name="editor")
        fake_user = SimpleNamespace(
            id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            email="charlie@example.com",
            full_name="Charlie Brown",
            roles=[role_a, role_b],
        )
        ctx = UserContext.from_user(fake_user)
        assert ctx.id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        assert ctx.email == "charlie@example.com"
        assert ctx.name == "Charlie Brown"
        assert ctx.roles == ["admin", "editor"]
        # The user row carries no tenant; the resolver supplies it per request.
        assert ctx.tenant_id is None

    async def test_from_user_name_fallback_to_email(self):
        """When full_name is None, ctx.name falls back to the user's email."""
        import uuid
        from types import SimpleNamespace

        fake_user = SimpleNamespace(
            id=uuid.uuid4(),
            email="dana@example.com",
            full_name=None,
            roles=[],
            tenant_id=None,
        )
        ctx = UserContext.from_user(fake_user)
        assert ctx.name == "dana@example.com"
        assert ctx.tenant_id is None

    async def test_from_user_no_roles(self):
        """from_user with empty roles produces an empty list."""
        import uuid
        from types import SimpleNamespace

        fake_user = SimpleNamespace(
            id=uuid.uuid4(),
            email="eve@example.com",
            full_name="Eve",
            roles=[],
            tenant_id=None,
        )
        ctx = UserContext.from_user(fake_user)
        assert ctx.roles == []


class TestUserContextRoles:
    async def test_has_role(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["admin", "user"])
        assert ctx.has_role("admin") is True
        assert ctx.has_role("superadmin") is False

    async def test_has_any_role(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["editor"])
        assert ctx.has_any_role(["admin", "editor"]) is True
        assert ctx.has_any_role(["admin", "superadmin"]) is False

    async def test_has_any_role_empty_user_roles(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=[])
        assert ctx.has_any_role(["admin"]) is False

    async def test_has_any_role_empty_check_list(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["admin"])
        assert ctx.has_any_role([]) is False

    async def test_has_role_case_sensitive(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["Admin"])
        assert ctx.has_role("admin") is False
        assert ctx.has_role("Admin") is True


class TestUserContextDefaults:
    async def test_tenant_id_default_is_none(self):
        """Direct construction without tenant_id should default to None."""
        ctx = UserContext(id="1", email="a@b.com", name="A")
        assert ctx.tenant_id is None

    async def test_roles_default_is_empty_list(self):
        ctx = UserContext(id="1", email="a@b.com", name="A")
        assert ctx.roles == []

    async def test_permissions_default_is_empty_list(self):
        ctx = UserContext(id="1", email="a@b.com", name="A")
        assert ctx.permissions == []

    async def test_positional_construction_unchanged(self):
        ctx = UserContext("1", "a@b.com", "A", ["admin"], "t1")
        assert ctx.tenant_id == "t1"
        assert ctx.permissions == []


class TestUserContextPermissions:
    async def test_session_round_trip_keeps_permissions(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", permissions=["x.read", "x.write"])
        payload = ctx.to_session_dict()
        assert payload["permissions"] == ["x.read", "x.write"]
        assert UserContext.from_session_dict(payload) == ctx

    async def test_legacy_cookie_without_permissions_key(self):
        """A cookie written before the field existed still decodes."""
        payload = {"id": "1", "email": "a@b.com", "name": "A", "roles": [], "tenant_id": None}
        ctx = UserContext.from_session_dict(payload)
        assert ctx is not None
        assert ctx.permissions == []

    async def test_null_permissions_decodes_empty(self):
        payload = {"id": "1", "email": "a@b.com", "name": "A", "permissions": None}
        ctx = UserContext.from_session_dict(payload)
        assert ctx is not None
        assert ctx.permissions == []

    async def test_from_user_leaves_permissions_empty(self):
        from types import SimpleNamespace

        user = SimpleNamespace(id=1, email="a@b.com", full_name="A", roles=[])
        assert UserContext.from_user(user).permissions == []

    async def test_has_permission_exact_match(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", permissions=["x.read"])
        assert ctx.has_permission("x.read") is True
        assert ctx.has_permission("x.write") is False
        assert ctx.has_permission("x") is False
