"""OpenAPI security export and SM031 (#534)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from simple_module_core.diagnostics import DiagnosticLevel
from simple_module_core.public_routes import PublicRouteRegistry
from simple_module_hosting._openapi import (
    BEARER_SCHEME,
    SESSION_SCHEME,
    install_openapi_filter,
)
from simple_module_hosting._route_access import UNGUARDED_ROUTE_CODE, check_unguarded_api_routes
from simple_module_hosting.permissions import RequiresPermission
from simple_module_hosting.session import SESSION_COOKIE_NAME
from simple_module_hosting.token_guard import (
    GATE_AUTHENTICATED,
    Authenticated,
    TokenAllowed,
    dependant_gate_kinds,
    route_admits_tokens,
)

_BOTH = [{BEARER_SCHEME: []}, {SESSION_SCHEME: []}]


def _op(schema: dict, method: str, path: str) -> dict:
    return schema["paths"][path][method]


def _mini_app() -> FastAPI:
    app = FastAPI()
    app.state.public_routes = PublicRouteRegistry()
    app.state.public_routes.add_regex(r"/api/m/open/[^/]+$", methods={"GET"})
    router = APIRouter(prefix="/api/m")
    router.add_api_route("/guarded", lambda: None, dependencies=[Depends(RequiresPermission("x"))])
    router.add_api_route("/bare", lambda: None)
    router.add_api_route("/signed-in", lambda: None, dependencies=[Depends(Authenticated())])
    router.add_api_route("/open/{slug}", lambda slug: None)
    router.add_api_route("/open/{slug}", lambda slug: None, methods=["DELETE"])
    app.include_router(router)
    install_openapi_filter(app)
    return app


def test_both_schemes_are_declared(app) -> None:
    schemes = app.openapi()["components"]["securitySchemes"]
    assert schemes[BEARER_SCHEME] == {"type": "http", "scheme": "bearer"}
    assert schemes[SESSION_SCHEME] == {
        "type": "apiKey",
        "in": "cookie",
        "name": SESSION_COOKIE_NAME,
    }


def test_protected_operation_lists_both_schemes(app) -> None:
    assert _op(app.openapi(), "get", "/api/audit_log/")["security"] == _BOTH


def test_file_storage_public_operations_are_anonymous(app) -> None:
    schema = app.openapi()
    for path in (
        "/api/file-storage/public/{file_id}",
        "/api/file-storage/public/{file_id}/{filename}",
        "/api/file-storage/public/{file_id}/thumbnail",
    ):
        assert _op(schema, "get", path)["security"] == []
    assert _op(schema, "get", "/api/file-storage/files")["security"] == _BOTH


def test_every_operation_carries_security(app) -> None:
    for item in app.openapi()["paths"].values():
        for method, op in item.items():
            if isinstance(op, dict) and method != "parameters":
                assert "security" in op, op["operationId"]


def test_public_match_is_method_aware_on_a_templated_path() -> None:
    schema = _mini_app().openapi()
    assert _op(schema, "get", "/api/m/open/{slug}")["security"] == []
    assert _op(schema, "delete", "/api/m/open/{slug}")["security"] == _BOTH
    assert _op(schema, "get", "/api/m/bare")["security"] == _BOTH


def test_sm031_flags_unguarded_route_only() -> None:
    found = check_unguarded_api_routes(_mini_app())
    assert {d.code for d in found} == {UNGUARDED_ROUTE_CODE}
    assert all(d.level == DiagnosticLevel.WARNING for d in found)
    messages = " ".join(d.message for d in found)
    assert "GET /api/m/bare" in messages
    assert "DELETE /api/m/open/{slug}" in messages
    assert "/api/m/guarded" not in messages
    assert "GET /api/m/open" not in messages


def test_authenticated_silences_sm031() -> None:
    messages = " ".join(d.message for d in check_unguarded_api_routes(_mini_app()))
    assert "/api/m/signed-in" not in messages


def test_authenticated_is_a_gate_but_does_not_admit_tokens() -> None:
    router = APIRouter()
    router.add_api_route("/a", lambda: None, dependencies=[Depends(Authenticated())])
    router.add_api_route(
        "/b", lambda: None, dependencies=[Depends(Authenticated()), Depends(TokenAllowed())]
    )
    routes = {r.path: r for r in router.routes}
    assert GATE_AUTHENTICATED in dependant_gate_kinds(routes["/a"].dependant)
    assert route_admits_tokens(routes["/a"]) is False
    assert route_admits_tokens(routes["/b"]) is True


def test_real_app_has_no_unguarded_api_routes(app) -> None:
    assert check_unguarded_api_routes(app) == []
