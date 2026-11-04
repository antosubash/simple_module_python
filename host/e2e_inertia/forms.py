"""Two isolated form bags and FastAPI's automatic request-validation path."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import ValidationError, field_validator
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.inertia_utils import redirect_back_with_errors, validation_errors_to_dict
from sqlmodel import Field, SQLModel
from starlette.responses import RedirectResponse

from host.e2e_inertia.constants import PAGE_FORMS, ROUTE_PREFIX

router = APIRouter()

_FORMS_URL = f"{ROUTE_PREFIX}/forms"


class FormInput(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=1, max_length=254)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str):
        if not value.strip():
            raise ValueError("name_required")
        return value

    @field_validator("email")
    @classmethod
    def email_contains_at(cls, value: str):
        if "@" not in value:
            raise ValueError("email_invalid")
        return value


@router.get("/forms")
async def forms(inertia: InertiaDep, success: Literal["", "default", "second", "validated"] = ""):
    return await inertia.render(PAGE_FORMS, {"success": success})


@router.post("/forms/validated")
async def validated(data: FormInput):
    return RedirectResponse(f"{_FORMS_URL}?success=validated", status_code=303)


@router.post("/forms/{bag}")
async def submit(bag: Literal["default", "second"], request: Request, data: dict[str, object]):
    try:
        FormInput.model_validate(data)
    except ValidationError as exc:
        errors = {field: f"Invalid {field}" for field in validation_errors_to_dict(exc)}
        return redirect_back_with_errors(request, errors)
    return RedirectResponse(f"{_FORMS_URL}?success={bag}", status_code=303)
