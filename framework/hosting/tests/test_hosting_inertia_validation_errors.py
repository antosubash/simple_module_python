"""Form validation keys and error-bag redirects (#776, #777)."""

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from simple_module_hosting.inertia_utils import (
    redirect_back_with_errors,
    validation_errors_to_dict,
)
from simple_module_inertia import Inertia, InertiaConfig, inertia_dependency_factory
from sqlmodel import SQLModel
from starlette.middleware.sessions import SessionMiddleware


class Order(SQLModel):
    quantity: int | bool
    tags: list[int]


def test_hosting_validation_uses_form_fields_and_first_message():
    with pytest.raises(ValidationError) as caught:
        Order.model_validate({"quantity": "lots", "tags": ["x"]})

    assert validation_errors_to_dict(caught.value) == {
        "quantity": "Input should be a valid integer, unable to parse string as an integer",
        "tags": "Input should be a valid integer, unable to parse string as an integer",
    }


def test_hosting_redirect_flashes_requested_error_bag():
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-inertia-error-bag", b"createUser")],
            "session": {},
        }
    )
    redirect_back_with_errors(request, {"email": "taken"})
    assert request.session["_errors"] == {"createUser": {"email": "taken"}}


@pytest.mark.parametrize("bag", [None, "createUser", ""])
async def test_hosting_error_bag_round_trip(tmp_path, bag):
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="validation-test")
    dep = inertia_dependency_factory(
        InertiaConfig(
            templates=Jinja2Templates(directory=str(tmp_path)),
            version="1.0",
            use_flash_errors=True,
        )
    )

    @app.post("/__repro/bag")
    async def submit(request: Request):
        return redirect_back_with_errors(request, {"email": "taken"})

    @app.get("/__repro/page")
    async def page(inertia: Inertia = Depends(dep)):
        return await inertia.render("Test/Validation", {})

    headers = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}
    if bag is not None:
        headers["X-Inertia-Error-Bag"] = bag
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/__repro/bag", headers={**headers, "Referer": "http://test/__repro/page"}
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/__repro/page"
        response = await client.get("/__repro/page", headers=headers)
        assert response.status_code == 200
        expected = {"email": "taken"} if bag is None else {bag: {"email": "taken"}}
        assert response.json()["props"]["errors"] == expected
        response = await client.get("/__repro/page", headers=headers)
        assert response.json()["props"]["errors"] == {}
