"""The create-setting form action, split out of ``views`` to keep it under the file cap."""

from __future__ import annotations

from fastapi import Request
from pydantic import ValidationError
from simple_module_hosting.inertia_utils import redirect_back_with_errors, validation_errors_to_dict
from starlette.responses import RedirectResponse

from settings._unique_write import DuplicateSettingError
from settings.constants import ERR_SETTING_EXISTS
from settings.contracts.schemas import SettingCreate, SettingScope
from settings.service import SettingService
from settings.tenant_scope import tenant_write_error


async def create_from_form(
    request: Request, service: SettingService, redirect_to: str
) -> RedirectResponse:
    """Validate and store a posted setting; field errors go back to the form."""
    body = await request.json()
    try:
        data = SettingCreate(**body)
    except ValidationError as exc:
        return redirect_back_with_errors(request, validation_errors_to_dict(exc))
    if data.scope is SettingScope.TENANT and (
        error := await tenant_write_error(request, data.scope_id, data.key, data.value)
    ):
        return redirect_back_with_errors(request, {"scope_id": error})
    try:
        await service.create(data)
    except DuplicateSettingError:
        return redirect_back_with_errors(request, {"key": ERR_SETTING_EXISTS})
    return RedirectResponse(redirect_to, status_code=303)
