"""Tests for the UserContext value object (construction, roles, tenant)."""

from __future__ import annotations

from auth.contracts.schemas import UserContext


class TestUserContext:
    async def test_from_keycloak_userinfo_basic(self):
        userinfo = {
            "sub": "user-123",
            "email": "alice@example.com",
            "name": "Alice Smith",
            "realm_access": {"roles": ["user", "editor"]},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.id == "user-123"
        assert ctx.email == "alice@example.com"
        assert ctx.name == "Alice Smith"
        assert ctx.roles == ["user", "editor"]

    async def test_from_keycloak_userinfo_fallback_username(self):
        userinfo = {
            "sub": "user-456",
            "email": "bob@example.com",
            "preferred_username": "bob",
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.name == "bob"

    async def test_from_keycloak_userinfo_missing_fields(self):
        userinfo = {}
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.id == ""
        assert ctx.email == ""
        assert ctx.name == ""
        assert ctx.roles == []

    async def test_has_role(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["admin", "user"])
        assert ctx.has_role("admin") is True
        assert ctx.has_role("superadmin") is False

    async def test_has_any_role(self):
        ctx = UserContext(id="1", email="a@b.com", name="A", roles=["editor"])
        assert ctx.has_any_role(["admin", "editor"]) is True
        assert ctx.has_any_role(["admin", "superadmin"]) is False


class TestUserContextTenantId:
    async def test_tenant_id_from_custom_claim(self):
        """UserContext should read a custom ``tenant_id`` claim from userinfo."""
        userinfo = {
            "sub": "user-123",
            "tenant_id": "acme-corp",
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id == "acme-corp"

    async def test_tenant_id_from_organization_claim(self):
        """UserContext should fall back to Keycloak's organization.id claim."""
        userinfo = {
            "sub": "user-123",
            "organization": {"id": "org-42", "name": "Acme"},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id == "org-42"

    async def test_tenant_id_custom_claim_takes_precedence(self):
        """Custom tenant_id claim should take precedence over organization.id."""
        userinfo = {
            "sub": "user-123",
            "tenant_id": "custom-tenant",
            "organization": {"id": "org-42"},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id == "custom-tenant"

    async def test_tenant_id_missing_is_none(self):
        """When no tenant claim is present, tenant_id should be None."""
        userinfo = {"sub": "user-123"}
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id is None

    async def test_tenant_id_organization_without_id_is_none(self):
        """An organization claim without an id should leave tenant_id as None."""
        userinfo = {
            "sub": "user-123",
            "organization": {"name": "no-id"},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id is None

    async def test_tenant_id_organization_as_non_dict_is_ignored(self):
        """A non-dict organization claim should not crash; tenant_id stays None."""
        userinfo = {
            "sub": "user-123",
            "organization": "not-a-dict",
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert ctx.tenant_id is None

    async def test_tenant_id_default_is_none(self):
        """Direct construction without tenant_id should default to None."""
        ctx = UserContext(id="1", email="a@b.com", name="A")
        assert ctx.tenant_id is None


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


class TestUserContextAdvanced:
    async def test_from_keycloak_with_realm_access_roles(self):
        userinfo = {
            "sub": "u1",
            "name": "Admin",
            "email": "admin@test.com",
            "realm_access": {"roles": ["admin", "user"]},
        }
        ctx = UserContext.from_keycloak_userinfo(userinfo)
        assert "admin" in ctx.roles
        assert "user" in ctx.roles

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
