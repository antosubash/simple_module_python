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
            tenant_id="tenant-42",
        )
        ctx = UserContext.from_user(fake_user)
        assert ctx.id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        assert ctx.email == "charlie@example.com"
        assert ctx.name == "Charlie Brown"
        assert ctx.roles == ["admin", "editor"]
        assert ctx.tenant_id == "tenant-42"

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
