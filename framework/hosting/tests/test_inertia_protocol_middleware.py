"""Host regressions for the middleware-level Inertia protocol (#774, #775, #778)."""

import pytest
from fastapi.routing import APIRoute
from simple_module_hosting.inertia_deps import InertiaDep
from starlette.responses import RedirectResponse, Response


@pytest.mark.parametrize("status", [302, 307])
@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "QUERY"])
async def test_host_inertia_mutation_redirect_is_303(app, authenticated_client, method, status):
    async def endpoint():
        return RedirectResponse("/__repro/page", status_code=status)

    app.router.routes.insert(0, APIRoute("/__repro/mutate", endpoint, methods=[method]))
    response = await authenticated_client.request(
        method, "/__repro/mutate", headers={"X-Inertia": "true"}
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/__repro/page"
    assert response.headers["cache-control"] == "private, no-store"
    assert "X-Inertia" in response.headers["vary"]


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_host_inertia_fragment_redirect(app, authenticated_client, status):
    async def endpoint():
        return RedirectResponse("/__repro/page#danger-zone", status_code=status)

    app.router.routes.insert(0, APIRoute("/__repro/fragment", endpoint, methods=["POST"]))
    response = await authenticated_client.post("/__repro/fragment", headers={"X-Inertia": "true"})
    assert response.status_code == 409
    assert response.headers["x-inertia-redirect"] == "/__repro/page#danger-zone"
    assert response.content == b""
    assert "location" not in response.headers
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    "referer,back",
    [("http://testserver/before?q=1", "/before?q=1"), ("https://evil.example/before", "/")],
)
async def test_host_inertia_empty_response_redirects_back(app, authenticated_client, referer, back):
    async def endpoint():
        return Response(status_code=200)

    app.router.routes.insert(0, APIRoute("/__repro/empty", endpoint, methods=["POST"]))
    response = await authenticated_client.post(
        "/__repro/empty", headers={"X-Inertia": "true", "Referer": referer}
    )
    assert response.status_code == 303
    assert response.headers["location"] == back


async def test_host_missing_version_conflicts_and_document_has_one_page(app, authenticated_client):
    async def page(inertia: InertiaDep):
        return await inertia.render("Repro/Page", {"greeting": "hi"})

    app.router.routes.insert(0, APIRoute("/__repro/page", page, methods=["GET"]))
    # Remove the fixture's default to simulate an old or incomplete client.
    authenticated_client.headers.pop("X-Inertia-Version", None)
    response = await authenticated_client.get("/__repro/page", headers={"X-Inertia": "true"})
    assert response.status_code == 409
    assert response.headers["x-inertia-version"]
    document = await authenticated_client.get("/__repro/page")
    assert document.status_code == 200
    assert '<script data-page="app" type="application/json">' in document.text
    assert '<div id="app"></div>' in document.text
    assert "data-page='" not in document.text


async def test_host_error_page_keeps_version_conflict_headers(authenticated_client):
    version = authenticated_client.headers.pop("X-Inertia-Version")
    response = await authenticated_client.get("/__repro/missing", headers={"X-Inertia": "true"})
    assert response.status_code == 409
    assert response.headers["x-inertia-version"] == version
    assert response.headers["x-inertia-location"].endswith("/__repro/missing")


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
async def test_module_middleware_redirect_after_mutation_is_normalised(app, client, method):
    """The auth middleware's login redirect for an expired session is outside the
    route, so InertiaMiddleware must wrap module middleware to turn it into a 303."""

    async def endpoint():
        return Response(status_code=204)

    app.router.routes.insert(0, APIRoute("/__repro/protected", endpoint, methods=[method]))
    response = await client.request(method, "/__repro/protected", headers={"X-Inertia": "true"})
    assert response.status_code not in (301, 302, 307, 308), response.status_code
