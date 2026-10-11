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


def test_records_only_modules_with_view_routes_in_order():
    app = FastAPI()
    for m in (
        _module("Api", "", views=False, api=True),
        _module("Root", "", views=True),
        _module("Blog", "/blog", views=True),
        _module("Empty", "/empty", views=False),
    ):
        wire_module_routes(app, m)
    assert list(app.state.view_prefixes.items()) == [("Root", ""), ("Blog", "/blog")]
