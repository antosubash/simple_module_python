"""Shared Inertia utilities for form-action view endpoints."""

from __future__ import annotations

from fastapi import Request
from pydantic import ValidationError
from starlette.responses import RedirectResponse

SESSION_ERRORS_KEY = "_errors"


def validation_errors_to_dict(exc: ValidationError) -> dict[str, str]:
    """Flatten a Pydantic ValidationError — takes only the last loc segment
    so nested model paths don't leak into the frontend field keys."""
    errors: dict[str, str] = {}
    for error in exc.errors():
        field = str(error["loc"][-1]) if error["loc"] else "general"
        errors[field] = error["msg"]
    return errors


def redirect_back_with_errors(request: Request, errors: dict[str, str]) -> RedirectResponse:
    """Store validation errors in the session and redirect to the referring page."""
    request.session[SESSION_ERRORS_KEY] = errors
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=303)
