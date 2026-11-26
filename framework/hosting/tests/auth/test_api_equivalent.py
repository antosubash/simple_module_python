"""``api_equivalent`` / ``api_exempt`` markers and the view-route walker."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from simple_module_hosting.auth.api_equivalent import (
    EXEMPT_LOGOUT,
    EXEMPT_SETUP,
    ApiEquivalent,
    ApiExempt,
    api_equivalent,
    api_exempt,
    dependant_api_declarations,
    view_route_offenders,
)
from simple_module_hosting.auth.permissions import RequiresPermission
from simple_module_hosting.auth.token_guard import page_route

_PERM = "things.edit"


def _app_with_api() -> FastAPI:
    app = FastAPI()
    app.put("/api/things/{thing_id}", dependencies=[Depends(RequiresPermission(_PERM))])(
        lambda thing_id: None
    )
    app.delete("/api/things/{thing_id}")(lambda thing_id: None)  # no gate: refuses tokens
    return app


def _view(app: FastAPI, *deps, method: str = "POST", router_deps=()) -> None:
    router = APIRouter(dependencies=[Depends(page_route), *router_deps])
    router.add_api_route("/{thing_id}", lambda thing_id: None, methods=[method], dependencies=deps)
    app.include_router(router, prefix="/things")


def test_api_equivalent_carries_its_declaration():
    marker = api_equivalent("put", "/api/things/{thing_id}")
    app = FastAPI()
    app.post("/x", dependencies=[Depends(marker)])(lambda: {"ok": True})
    route = next(r for r in app.routes if getattr(r, "path", "") == "/x")
    assert dependant_api_declarations(route.dependant) == [
        ApiEquivalent("PUT", "/api/things/{thing_id}")
    ]
    assert TestClient(app).post("/x").json() == {"ok": True}  # a no-op dependency


def test_api_exempt_carries_its_reason():
    app = FastAPI()
    app.post("/logout", dependencies=[Depends(api_exempt(EXEMPT_LOGOUT))])(lambda: None)
    route = next(r for r in app.routes if getattr(r, "path", "") == "/logout")
    assert dependant_api_declarations(route.dependant) == [ApiExempt(EXEMPT_LOGOUT)]


@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/api/things"), ("POST", "/things"), ("TRACE", "/api/x")]
)
def test_api_equivalent_rejects_bad_targets(method: str, path: str):
    with pytest.raises(ValueError):
        api_equivalent(method, path)


def test_api_exempt_needs_a_reason():
    with pytest.raises(ValueError):
        api_exempt("  ")


def test_declared_route_to_token_admitting_api_passes():
    app = _app_with_api()
    _view(app, Depends(api_equivalent("PUT", "/api/things/{thing_id}")))
    assert view_route_offenders(app) == []


def test_exempt_route_passes():
    app = _app_with_api()
    _view(app, Depends(api_exempt(EXEMPT_LOGOUT)))
    assert view_route_offenders(app) == []


def test_router_level_declaration_counts():
    app = _app_with_api()
    _view(app, router_deps=[Depends(api_exempt(EXEMPT_LOGOUT))])
    assert view_route_offenders(app) == []


def test_get_routes_need_nothing():
    app = _app_with_api()
    _view(app, method="GET")
    assert view_route_offenders(app) == []


def test_undeclared_route_is_an_offender():
    app = _app_with_api()
    _view(app)
    assert view_route_offenders(app) == [
        "POST /things/{thing_id}: no api_equivalent or api_exempt declaration"
    ]


def test_exempt_and_equivalent_together_are_an_offender():
    app = _app_with_api()
    _view(
        app,
        Depends(api_exempt(EXEMPT_LOGOUT)),
        Depends(api_equivalent("PUT", "/api/things/{thing_id}")),
    )
    assert view_route_offenders(app) == [
        "POST /things/{thing_id}: declares both api_exempt and api_equivalent"
    ]


def test_two_exemptions_are_an_offender():
    app = _app_with_api()
    _view(app, Depends(api_exempt(EXEMPT_LOGOUT)), Depends(api_exempt(EXEMPT_SETUP)))
    assert view_route_offenders(app) == [
        "POST /things/{thing_id}: 2 api_exempt declarations, need exactly one"
    ]


def test_one_equivalent_per_scope_validates_each():
    app = _app_with_api()
    app.put("/api/tenant/{thing_id}", dependencies=[Depends(RequiresPermission(_PERM))])(
        lambda thing_id: None
    )
    _view(
        app,
        Depends(api_equivalent("PUT", "/api/things/{thing_id}")),
        Depends(api_equivalent("PUT", "/api/tenant/{thing_id}")),
    )
    assert view_route_offenders(app) == []
    _view(
        app,
        Depends(api_equivalent("PUT", "/api/things/{thing_id}")),
        Depends(api_equivalent("PUT", "/api/missing/{thing_id}")),
    )
    assert view_route_offenders(app) == [
        "POST /things/{thing_id}: PUT /api/missing/{thing_id} is not a registered route"
    ]


def test_mounted_view_route_is_walked():
    app = _app_with_api()
    sub = FastAPI()
    sub.post("/{thing_id}")(lambda thing_id: None)
    app.mount("/sub", sub)
    assert view_route_offenders(app) == [
        "POST /sub/{thing_id}: no api_equivalent or api_exempt declaration"
    ]


def test_mounted_api_target_resolves():
    app = FastAPI()
    sub = FastAPI()
    sub.put("/things/{thing_id}", dependencies=[Depends(RequiresPermission(_PERM))])(
        lambda thing_id: None
    )
    app.mount("/api/sub", sub)
    _view(app, Depends(api_equivalent("PUT", "/api/sub/things/{thing_id}")))
    assert view_route_offenders(app) == []


def test_shadowed_target_is_judged_on_the_route_that_dispatches():
    app = FastAPI()
    app.put("/api/things/{thing_id}")(lambda thing_id: None)  # first: no gate, refuses
    app.put("/api/things/{thing_id}", dependencies=[Depends(RequiresPermission(_PERM))])(
        lambda thing_id: None
    )
    _view(app, Depends(api_equivalent("PUT", "/api/things/{thing_id}")))
    assert view_route_offenders(app) == [
        "POST /things/{thing_id}: PUT /api/things/{thing_id} refuses API tokens"
    ]


def test_shadowed_refusing_duplicate_does_not_matter():
    app = _app_with_api()  # gated PUT registered first
    app.put("/api/things/{thing_id}")(lambda thing_id: None)
    _view(app, Depends(api_equivalent("PUT", "/api/things/{thing_id}")))
    assert view_route_offenders(app) == []


def test_unknown_target_is_an_offender():
    app = _app_with_api()
    _view(app, Depends(api_equivalent("PATCH", "/api/things/{thing_id}")))
    assert view_route_offenders(app) == [
        "POST /things/{thing_id}: PATCH /api/things/{thing_id} is not a registered route"
    ]


def test_target_refusing_tokens_is_an_offender():
    app = _app_with_api()
    _view(app, Depends(api_equivalent("DELETE", "/api/things/{thing_id}")), method="DELETE")
    assert view_route_offenders(app) == [
        "DELETE /things/{thing_id}: DELETE /api/things/{thing_id} refuses API tokens"
    ]


def test_earlier_param_route_shadows_a_later_literal_target():
    app = FastAPI()
    app.post("/api/items/{item_id}")(lambda item_id: None)  # first: no gate, refuses
    app.post("/api/items/special", dependencies=[Depends(RequiresPermission(_PERM))])(lambda: None)
    _view(app, Depends(api_equivalent("POST", "/api/items/special")))
    assert view_route_offenders(app) == [
        "POST /things/{thing_id}: POST /api/items/special refuses API tokens"
    ]


def test_literal_route_first_is_the_one_a_literal_target_reaches():
    app = FastAPI()
    app.post("/api/items/special", dependencies=[Depends(RequiresPermission(_PERM))])(lambda: None)
    app.post("/api/items/{item_id}")(lambda item_id: None)
    _view(app, Depends(api_equivalent("POST", "/api/items/special")))
    assert view_route_offenders(app) == []


def test_typo_literal_target_is_not_a_registered_route():
    app = FastAPI()
    app.post("/api/items/{item_id}", dependencies=[Depends(RequiresPermission(_PERM))])(
        lambda item_id: None
    )
    _view(app, Depends(api_equivalent("POST", "/api/items/archvie")))
    assert view_route_offenders(app) == [
        "POST /things/{thing_id}: POST /api/items/archvie is not a registered route"
    ]


def test_int_route_does_not_shadow_a_later_literal_target():
    app = FastAPI()
    app.post("/api/items/{item_id:int}")(lambda item_id: None)  # refuses, but int-only
    app.post("/api/items/special", dependencies=[Depends(RequiresPermission(_PERM))])(lambda: None)
    _view(app, Depends(api_equivalent("POST", "/api/items/special")))
    assert view_route_offenders(app) == []


def test_converter_template_is_declared_without_the_converter():
    app = FastAPI()
    app.post("/api/items/{item_id:int}", dependencies=[Depends(RequiresPermission(_PERM))])(
        lambda item_id: None
    )
    _view(app, Depends(api_equivalent("POST", "/api/items/{item_id}")))
    assert view_route_offenders(app) == []


def test_earlier_admitting_literal_does_not_vouch_for_a_refusing_int_target():
    app = FastAPI()
    app.post("/api/items/1", dependencies=[Depends(RequiresPermission(_PERM))])(lambda: None)
    app.post("/api/items/{item_id:int}")(lambda item_id: None)  # target refuses tokens
    _view(app, Depends(api_equivalent("POST", "/api/items/{item_id}")))
    assert view_route_offenders(app) == [
        "POST /things/{thing_id}: POST /api/items/{item_id} refuses API tokens"
    ]
