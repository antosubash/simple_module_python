"""Tests for auth FastAPI dependencies (get_current_user, require_permission)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from auth.contracts.schemas import UserContext
from auth.deps import get_current_user, require_permission
from fastapi import HTTPException


class TestGetCurrentUser:
    async def test_raises_401_when_no_user(self):
        """get_current_user raises 401 when request.state has no user."""
        request = MagicMock()
        del request.state.user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401

    async def test_returns_user_when_present(self):
        """get_current_user returns the user from request.state."""
        user = UserContext(id="u1", email="u@test.com", name="User", roles=["user"])
        request = MagicMock()
        request.state.user = user

        result = await get_current_user(request)
        assert result.id == "u1"


class TestRequirePermission:
    async def test_raises_403_when_missing_permission(self, app):
        """The require_permission check raises 403 when user lacks permissions."""
        dep = require_permission("products.delete")
        check_fn = dep.dependency

        request = MagicMock()
        request.app.state.perm_registry = app.state.perm_registry

        user = UserContext(id="u1", email="u@test.com", name="User", roles=["viewer"])

        with pytest.raises(HTTPException) as exc_info:
            await check_fn(request, user)
        assert exc_info.value.status_code == 403

    async def test_admin_bypasses_permission_check(self, app):
        """The require_permission check allows admin users through."""
        dep = require_permission("products.delete")
        check_fn = dep.dependency

        request = MagicMock()
        request.app.state.perm_registry = app.state.perm_registry

        admin_user = UserContext(id="a1", email="admin@test.com", name="Admin", roles=["admin"])
        await check_fn(request, admin_user)


class TestRequirePermissionAdvanced:
    async def test_multiple_permissions_any_match(self, app):
        """User with any of the required permissions should pass."""
        dep = require_permission("products.view", "products.edit")
        check_fn = dep.dependency

        request = MagicMock()
        request.app.state.perm_registry = app.state.perm_registry

        admin = UserContext(id="a1", email="a@t.com", name="Admin", roles=["admin"])
        await check_fn(request, admin)

    async def test_non_admin_without_permission_fails(self, app):
        dep = require_permission("products.delete")
        check_fn = dep.dependency

        request = MagicMock()
        request.app.state.perm_registry = app.state.perm_registry

        user = UserContext(id="u1", email="u@t.com", name="User", roles=["user"])
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(request, user)
        assert exc_info.value.status_code == 403
        assert "products.delete" in str(exc_info.value.detail)
