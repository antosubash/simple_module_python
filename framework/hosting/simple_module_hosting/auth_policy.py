"""Host-owned cookie security and post-login destination for every provider."""

from __future__ import annotations

from fastapi import FastAPI
from simple_module_core.environments import NON_PROD_ENVIRONMENTS

from simple_module_hosting._host_settings_support import DEFAULT_LOGIN_REDIRECT_URL
from simple_module_hosting.settings import Settings

_DASHBOARD_MODULE = "Dashboard"


def session_cookie_is_secure(settings: Settings) -> bool:
    """An explicit host choice wins; otherwise non-production permits HTTP."""
    if settings.session_cookie_secure is not None:
        return settings.session_cookie_secure
    return settings.environment not in NON_PROD_ENVIRONMENTS


def login_redirect_url(app: FastAPI, provider: str) -> str:
    """Resolve the live host destination, avoiding an absent Dashboard."""
    destination = app.state.host.settings.login_redirect_url
    if destination != DEFAULT_LOGIN_REDIRECT_URL:
        return destination
    if any(m.meta.name == _DASHBOARD_MODULE for m in app.state.sm.modules):
        return destination
    prefix = next(
        (prefix for name, prefix in app.state.sm.view_prefixes.items() if name != provider), None
    )
    return "/" if prefix is None else f"{prefix.rstrip('/')}/"
