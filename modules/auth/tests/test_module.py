"""Tests for AuthModule registration (metadata, menu, logout endpoint)."""

from __future__ import annotations

import httpx
from auth.module import AuthModule
from simple_module_core.menu import MenuRegistry


class TestAuthModuleRegistration:
    async def test_auth_module_has_correct_meta(self):
        mod = AuthModule()
        assert mod.meta.name == "Auth"
        assert mod.meta.route_prefix == "/auth"

    async def test_auth_module_registers_menu_items(self):
        mod = AuthModule()
        reg = MenuRegistry()
        mod.register_menu_items(reg)
        assert len(reg.all_items) == 1
        assert reg.all_items[0].label == "Logout"
        assert reg.all_items[0].url == "/auth/logout"

    async def test_auth_logout_endpoint_exists(self, client: httpx.AsyncClient):
        """The /auth/logout endpoint should exist (even if it redirects)."""
        resp = await client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 302
