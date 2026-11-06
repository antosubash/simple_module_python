"""Tests for AuthModule: meta-only after Keycloak removal."""

from __future__ import annotations

from auth.module import AuthModule
from simple_module_core.menu import MenuRegistry


class TestAuthModuleRegistration:
    async def test_auth_module_has_correct_meta(self):
        mod = AuthModule()
        assert mod.meta.name == "Auth"
        assert mod.meta.route_prefix == "/auth"

    async def test_auth_module_registers_no_menu_items(self):
        """AuthModule is now meta-only — it registers no menu items."""
        mod = AuthModule()
        reg = MenuRegistry()
        mod.register_menu_items(reg)
        assert len(reg.all_items) == 0

    async def test_auth_module_has_no_routes(self):
        """AuthModule no longer registers any routes — it's contracts-only."""
        from fastapi import APIRouter

        mod = AuthModule()
        api_router = APIRouter()
        view_router = APIRouter()
        mod.register_routes(api_router, view_router)
        assert len(api_router.routes) == 0
        assert len(view_router.routes) == 0
