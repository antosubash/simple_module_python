"""An Inertia form whose body fails FastAPI validation goes back with field errors.

Before, hosting's request-validation handler answered every browser-shaped
request with the 422 Error page ("The requested URL contains invalid
parameters."), so an Inertia ``useForm`` POST replaced the form with an error
page instead of showing messages next to its fields.
"""

from __future__ import annotations

import httpx
import pytest
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_test import inertia_page
from sqlmodel import SQLModel

_FORM = "/__test/body-validation/form"
_SUBMIT = "/__test/body-validation/submit"


def _inertia(client: httpx.AsyncClient) -> dict[str, str]:
    return {"X-Inertia": "true", "Referer": f"{client.base_url}{_FORM}"}


class _Signup(SQLModel):
    name: str
    age: int


@pytest.fixture
async def form_client(app, authenticated_client: httpx.AsyncClient) -> httpx.AsyncClient:
    async def form(inertia: InertiaDep):
        return await inertia.render("Probe/Form")

    async def submit(data: _Signup) -> dict[str, str]:
        return {"name": data.name}

    async def lookup(age: int) -> dict[str, int]:
        return {"age": age}

    async def remove(item_id: int) -> dict[str, int]:
        return {"removed": item_id}

    app.router.add_api_route(_FORM, form, methods=["GET"])
    app.router.add_api_route(f"{_SUBMIT}/{{item_id}}", remove, methods=["DELETE"])
    app.router.add_api_route(_SUBMIT, submit, methods=["POST", "PUT", "PATCH"])
    app.router.add_api_route(_SUBMIT, lookup, methods=["GET"])
    return authenticated_client


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
async def test_inertia_submission_redirects_back_with_field_errors(
    form_client: httpx.AsyncClient, method: str
) -> None:
    resp = await form_client.request(
        method, _SUBMIT, json={"age": "old"}, headers=_inertia(form_client)
    )
    assert resp.status_code == 303
    assert resp.headers["location"].endswith(_FORM)

    page = inertia_page(await form_client.get(_FORM, headers={"X-Inertia": "true"}))
    assert set(page.props["errors"]) == {"name", "age"}
    assert page.props["errors"]["age"].startswith("Input should be a valid integer")


async def test_error_bag_scopes_the_errors(form_client: httpx.AsyncClient) -> None:
    headers = {**_inertia(form_client), "X-Inertia-Error-Bag": "signup"}
    resp = await form_client.post(_SUBMIT, json={}, headers=headers)
    assert resp.status_code == 303

    page = inertia_page(await form_client.get(_FORM, headers={"X-Inertia": "true"}))
    assert set(page.props["errors"]) == {"signup"}
    assert set(page.props["errors"]["signup"]) == {"name", "age"}


async def test_inertia_get_with_bad_query_keeps_the_error_page(
    form_client: httpx.AsyncClient,
) -> None:
    resp = await form_client.get(f"{_SUBMIT}?age=old", headers={"X-Inertia": "true"})
    assert resp.status_code == 422
    assert inertia_page(resp).component == "Error"


async def test_plain_browser_post_keeps_the_error_page(form_client: httpx.AsyncClient) -> None:
    resp = await form_client.post(_SUBMIT, json={}, headers={"Accept": "text/html"})
    assert resp.status_code == 422
    assert inertia_page(resp).component == "Error"


async def test_api_client_keeps_json_detail(form_client: httpx.AsyncClient) -> None:
    resp = await form_client.post(_SUBMIT, json={}, headers={"Accept": "application/json"})
    assert resp.status_code == 422
    assert {err["loc"][-1] for err in resp.json()["detail"]} == {"name", "age"}


async def test_invalid_path_param_keeps_the_error_page(form_client: httpx.AsyncClient) -> None:
    """No form field can show a bad path value; a silent redirect would hide it."""
    resp = await form_client.delete(f"{_SUBMIT}/abc", headers=_inertia(form_client))
    assert resp.status_code == 422
    assert inertia_page(resp).component == "Error"


async def test_only_body_errors_reach_the_form(app, form_client: httpx.AsyncClient) -> None:
    """A bad query value next to a bad body must not flash a stray field error."""

    async def paged(data: _Signup, page: int) -> dict[str, int]:
        return {"page": page}

    app.router.add_api_route(f"{_SUBMIT}-paged", paged, methods=["POST"])
    resp = await form_client.post(
        f"{_SUBMIT}-paged?page=x", json={"age": "old"}, headers=_inertia(form_client)
    )
    assert resp.status_code == 303
    page = inertia_page(await form_client.get(_FORM, headers={"X-Inertia": "true"}))
    assert set(page.props["errors"]) == {"name", "age"}
