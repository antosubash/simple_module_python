"""wire_module_routes records which modules actually mount view routes (#435)."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_hosting._module_routes import wire_module_routes


def _module(name: str, view_prefix: str, *, views: bool, api: bool = False) -> ModuleBase:
    class _M(ModuleBase):
        meta = ModuleMeta(name=name, view_prefix=view_prefix, route_prefix=f"/api/{name}")

        def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
            if views:
                view_router.add_api_route("/", lambda: "ok", methods=["GET"])
            if api:
                api_router.add_api_route("/", lambda: "ok", methods=["GET"])

    return _M()


def test_returns_whether_module_mounted_view_routes():
    app = FastAPI()
    assert wire_module_routes(app, _module("Root", "", views=True)) is True
    assert wire_module_routes(app, _module("Blog", "/blog", views=True)) is True
    assert wire_module_routes(app, _module("Api", "", views=False, api=True)) is False
    assert wire_module_routes(app, _module("Empty", "/empty", views=False)) is False


def test_services_view_prefixes_follow_discovery_order(app):
    names = [m.meta.name for m in app.state.sm.modules]
    recorded = list(app.state.sm.view_prefixes)
    assert recorded == [n for n in names if n in recorded]
    # Real module set: Users and Dashboard serve views, and each records its
    # own prefix, not a placeholder.
    by_name = {m.meta.name: m.meta.view_prefix for m in app.state.sm.modules}
    assert {"Users", "Dashboard"} <= set(recorded)
    assert all(app.state.sm.view_prefixes[n] == by_name[n] for n in recorded)
