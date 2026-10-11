"""Login fallback with a module mounted at the root (#435)."""

from __future__ import annotations

import pytest


def _fallback_url(app, prefixes: dict[str, str]) -> str:
    """Run the login fallback against a Dashboard-less module set (#435)."""
    from users.startup import apply_login_redirect_fallback

    sm = app.state.sm
    saved_mods, saved_prefixes = sm.modules, dict(sm.view_prefixes)
    settings = app.state.users.settings
    saved_url = settings.login_redirect_url
    object.__setattr__(sm, "modules", tuple(m for m in saved_mods if m.meta.name != "Dashboard"))
    sm.view_prefixes.clear()
    sm.view_prefixes.update(prefixes)
    settings.login_redirect_url = "/dashboard/"
    try:
        apply_login_redirect_fallback(app, settings, "Users", "/dashboard/")
        return settings.login_redirect_url
    finally:
        object.__setattr__(sm, "modules", saved_mods)
        sm.view_prefixes.clear()
        sm.view_prefixes.update(saved_prefixes)
        settings.login_redirect_url = saved_url


@pytest.mark.anyio
async def test_login_redirect_fallback_prefers_root_mounted_module(users_app):
    """#435: a module that serves views at ``/`` (view_prefix == "") wins."""
    assert _fallback_url(users_app, {"Users": "/users", "Home": "", "Other": "/o"}) == "/"


@pytest.mark.anyio
async def test_login_redirect_fallback_skips_api_only_module(users_app):
    """An API-only module also has view_prefix == "" but is not in the map."""
    assert _fallback_url(users_app, {"Users": "/users", "Other": "/o"}) == "/o/"
