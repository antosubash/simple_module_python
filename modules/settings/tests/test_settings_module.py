"""Module registration + constant invariants for the Settings module."""

from __future__ import annotations

from settings.constants import (
    ALL_PERMISSIONS,
    ALL_SCOPES,
    PERM_CREATE,
    PERM_DELETE,
    PERM_EDIT,
    PERM_VIEW,
    STATUS_CONFLICT,
    STATUS_CREATED,
    STATUS_NO_CONTENT,
    STATUS_NOT_FOUND,
)


class TestSettingsModuleRegistration:
    async def test_permissions_registered(self, app):
        perms = set(app.state.sm.permissions.all_permissions)
        for p in (PERM_VIEW, PERM_CREATE, PERM_EDIT, PERM_DELETE):
            assert p in perms

    async def test_all_permissions_unique(self):
        assert len(ALL_PERMISSIONS) == len(set(ALL_PERMISSIONS))

    async def test_all_scopes(self):
        assert ALL_SCOPES == ("system", "tenant", "user")

    async def test_status_constants(self):
        assert STATUS_CREATED == 201
        assert STATUS_NO_CONTENT == 204
        assert STATUS_NOT_FOUND == 404
        assert STATUS_CONFLICT == 409

    async def test_view_page_literals_match_constants(self):
        """Views use literal inertia.render(...) strings so SM003 can detect
        them — this guards the literals against drifting from the constants."""
        from pathlib import Path

        from settings.constants import PAGE_BROWSE, PAGE_CREATE, PAGE_EDIT

        views_path = Path(__file__).parent.parent / "settings" / "endpoints" / "views.py"
        views = views_path.read_text()
        assert f'"{PAGE_BROWSE}"' in views
        assert f'"{PAGE_CREATE}"' in views
        assert f'"{PAGE_EDIT}"' in views
