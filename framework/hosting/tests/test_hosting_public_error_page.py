"""Modules can use the public renderer with standard content negotiation (#684)."""

import pytest
from fastapi import Request


@pytest.mark.parametrize(
    "headers, json_response",
    [
        ({"Accept": "application/json"}, True),
        ({"Accept": "text/html"}, False),
        ({"Accept": "application/json", "X-Inertia": "true"}, False),
    ],
)
async def test_public_renderer_negotiates_and_preserves_status_and_headers(
    app, authenticated_client, headers, json_response
):
    from simple_module_hosting import render_error_page

    async def custom_error(request: Request):
        return await render_error_page(
            request, 429, detail="Try later", headers={"Retry-After": "30"}
        )

    app.add_api_route("/custom-error", custom_error)
    response = await authenticated_client.get("/custom-error", headers=headers)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    if json_response:
        assert response.json() == {"detail": "Try later"}
    elif "X-Inertia" in headers:
        assert response.json()["component"] == "Error"
        assert response.json()["props"]["message"] == "Try later"
    else:
        assert "data-page" in response.text
        assert "Try later" in response.text
