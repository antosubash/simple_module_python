"""RequiresResource over HTTP: 404 vs 403, token gating, list counts (GH #526)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

import httpx
import pytest
from _resacc_models import EDITOR, OWNER, POLICY, SHARED, STRANGER, ResaccDoc, seed
from fastapi import Depends, FastAPI, Request
from simple_module_core.resources import ACTION_EDIT, ACTION_VIEW, ResourcePrincipal
from simple_module_db import PageParams, paginate
from simple_module_hosting.resource_deps import RequiresResource, resource_principal
from simple_module_hosting.token_guard import route_admits_tokens, token_route_guard
from sqlmodel import select


@dataclass
class _User:
    id: uuid.UUID
    roles: list[str] = field(default_factory=lambda: ["user"])
    permissions: list[str] = field(default_factory=list)
    scopes: list[str] | None = None


def _doc_stmt(doc_id: uuid.UUID):
    return select(ResaccDoc).where(ResaccDoc.id == doc_id)


def _app(db_state, user: _User | None) -> FastAPI:
    app = FastAPI(dependencies=[Depends(token_route_guard)])
    app.state.sm = SimpleNamespace(db=db_state, permissions=None, i18n_registry=None)

    @app.get("/items")
    async def list_docs(who: ResourcePrincipal = Depends(resource_principal)) -> dict:
        factory = db_state.session_factory
        async with factory() as session:
            stmt = POLICY.filter(who, ACTION_VIEW, select(ResaccDoc).order_by(ResaccDoc.title))
            page = await paginate(session, stmt, PageParams())
        return {"total": page.total, "titles": [d.title for d in page.items]}

    @app.get("/items/{doc_id}")
    async def view(doc=Depends(RequiresResource(POLICY, ACTION_VIEW, _doc_stmt))) -> dict:
        return {"title": doc.title}

    @app.patch("/items/{doc_id}")
    async def edit(doc=Depends(RequiresResource(POLICY, ACTION_EDIT, _doc_stmt))) -> dict:
        return {"title": doc.title}

    gate = RequiresResource(POLICY, ACTION_VIEW, _doc_stmt, permission="resacc.view")

    @app.get("/api/items/{doc_id}")
    async def api_view(doc=Depends(gate)) -> dict:
        return {"title": doc.title}

    @app.middleware("http")
    async def fake_auth(request: Request, call_next):
        request.state.user = user
        return await call_next(request)

    return app


@pytest.fixture
async def docs(db_state, db_session):
    seeded = await seed(db_session)
    await db_session.commit()
    return {k: str(v.id) for k, v in seeded.items()}


async def _call(app: FastAPI, method: str, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.request(method, path)


async def test_non_shared_user_gets_404_and_row_absent_from_list(db_state, docs):
    app = _app(db_state, _User(STRANGER))
    assert (await _call(app, "GET", f"/items/{docs['private']}")).status_code == 404
    listing = (await _call(app, "GET", "/items")).json()
    assert listing == {"total": 2, "titles": ["other", "public"]}


async def test_owner_and_shared_user_see_the_row(db_state, docs):
    for who in (OWNER, SHARED):
        resp = await _call(_app(db_state, _User(who)), "GET", f"/items/{docs['private']}")
        assert resp.json() == {"title": "private"}
    listing = (await _call(_app(db_state, _User(SHARED)), "GET", "/items")).json()
    assert listing["total"] == 2 and "private" in listing["titles"]


async def test_viewer_gets_403_on_edit_editor_and_owner_pass(db_state, docs):
    path = f"/items/{docs['private']}"
    assert (await _call(_app(db_state, _User(SHARED)), "PATCH", path)).status_code == 403
    assert (await _call(_app(db_state, _User(EDITOR)), "PATCH", path)).status_code == 200
    assert (await _call(_app(db_state, _User(OWNER)), "PATCH", path)).status_code == 200


async def test_public_row_viewable_not_editable(db_state, docs):
    app = _app(db_state, _User(STRANGER))
    assert (await _call(app, "GET", f"/items/{docs['public']}")).status_code == 200
    assert (await _call(app, "PATCH", f"/items/{docs['public']}")).status_code == 403


async def test_unknown_id_is_404(db_state, docs):
    app = _app(db_state, _User(OWNER))
    assert (await _call(app, "GET", f"/items/{uuid.uuid4()}")).status_code == 404


async def test_token_refused_without_permission_argument(db_state, docs):
    token = _User(OWNER, roles=["admin"], scopes=["resacc.view"])
    app = _app(db_state, token)
    assert (await _call(app, "GET", f"/items/{docs['private']}")).status_code == 403
    assert (await _call(app, "GET", f"/api/items/{docs['private']}")).status_code == 200


async def test_token_with_permission_still_filtered_by_policy(db_state, docs):
    token = _User(STRANGER, permissions=["resacc.view"], scopes=["resacc.view"])
    resp = await _call(_app(db_state, token), "GET", f"/api/items/{docs['private']}")
    assert resp.status_code == 404


async def test_permission_argument_enforced_for_sessions(db_state, docs):
    resp = await _call(_app(db_state, _User(OWNER)), "GET", f"/api/items/{docs['private']}")
    assert resp.status_code == 403


def test_only_permission_variant_counts_as_token_gate(db_state):
    app = _app(db_state, None)
    routes = {(r.path, tuple(r.methods)): r for r in app.routes if hasattr(r, "dependant")}
    assert not route_admits_tokens(routes[("/items/{doc_id}", ("GET",))])
    assert route_admits_tokens(routes[("/api/items/{doc_id}", ("GET",))])
