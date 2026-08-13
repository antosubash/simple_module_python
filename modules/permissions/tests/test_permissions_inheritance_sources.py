"""Naming which role grants an inherited permission.

The user-grants screen drove its switch off `direct` alone, so a permission
the user genuinely holds through a role rendered exactly like one they did
not hold. `inherited_by` gives each row its source, which is also what tells
an admin which role to edit if they want the permission gone.
"""

from __future__ import annotations

from permissions.service import PermissionService
from simple_module_core.permissions import WILDCARD, PermissionRegistry
from sqlalchemy.ext.asyncio import AsyncSession


def _registry() -> PermissionRegistry:
    reg = PermissionRegistry()
    reg.add_group("Products", ["products.view", "products.create"])
    reg.add_group("Settings", ["settings.read", "settings.manage"])
    return reg


def _service(db_session: AsyncSession, reg: PermissionRegistry) -> PermissionService:
    return PermissionService(db_session, reg)


class TestResolveRoleSources:
    def test_maps_each_key_to_its_granting_role(self, db_session: AsyncSession):
        reg = _registry()
        reg.map_role("editor", ["products.view", "products.create"])
        svc = _service(db_session, reg)

        sources = svc._resolve_role_sources(["editor"])
        assert sources["products.view"] == ["editor"]
        assert sources["products.create"] == ["editor"]

    def test_two_roles_granting_one_key_both_appear(self, db_session: AsyncSession):
        """Revoking via one role would not be enough; the admin needs both."""
        reg = _registry()
        reg.map_role("editor", ["products.view"])
        reg.map_role("viewer", ["products.view"])
        svc = _service(db_session, reg)

        assert svc._resolve_role_sources(["viewer", "editor"])["products.view"] == [
            "editor",
            "viewer",
        ]

    def test_wildcard_role_claims_every_registered_key(self, db_session: AsyncSession):
        """An admin role holds everything — each row must still say why."""
        reg = _registry()
        reg.map_role("admin", [WILDCARD])
        svc = _service(db_session, reg)

        sources = svc._resolve_role_sources(["admin"])
        assert set(sources) == set(reg.all_permissions)
        assert sources["settings.manage"] == ["admin"]

    def test_no_roles_yields_nothing(self, db_session: AsyncSession):
        assert _service(db_session, _registry())._resolve_role_sources([]) == {}

    def test_unknown_role_contributes_nothing(self, db_session: AsyncSession):
        assert _service(db_session, _registry())._resolve_role_sources(["ghost"]) == {}


class TestUserPermissionsPayload:
    async def test_inherited_by_covers_keys_that_are_also_direct(
        self, db_session: AsyncSession
    ) -> None:
        """`inherited` drops direct duplicates; `inherited_by` must not, or a
        key granted both ways looks purely direct and revoking it silently
        leaves the role grant in place."""
        from users.constants import USER_ROLE_ID
        from users.models import Role, User

        reg = _registry()
        reg.map_role("editor", ["products.view"])

        role = Role(id=USER_ROLE_ID, name="editor", description="")
        user = User(email="e@example.com", hashed_password="x", is_active=True)
        user.roles = [role]
        db_session.add_all([role, user])
        await db_session.flush()

        svc = _service(db_session, reg)
        await svc.set_user_permissions(user.id, ["products.view"])
        out = await svc.get_user_permissions(user.id)

        assert out is not None
        assert "products.view" in out.direct
        assert "products.view" not in out.inherited
        assert out.inherited_by["products.view"] == ["editor"]
