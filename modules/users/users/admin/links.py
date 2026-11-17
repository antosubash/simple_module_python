"""Trusted origin shared by copied account links and emailed account links."""

from __future__ import annotations

from simple_module_core.app_state import get_host_services
from simple_module_hosting.public_urls import public_origin
from starlette.requests import Request


def admin_link_base(request: Request) -> str:
    users = request.app.state.users.settings
    host = getattr(get_host_services(request.app), "settings", None)
    return public_origin(host, users.base_url)
