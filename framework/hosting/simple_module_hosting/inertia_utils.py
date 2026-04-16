"""Shared Inertia utilities for form-action view endpoints."""

from __future__ import annotations

from fastapi import Request
from pydantic import ValidationError
from starlette.responses import RedirectResponse

from simple_module_hosting.redirects import safe_referer_or_root

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
    """Store validation errors in the session and redirect to the referring page.

    Uses ``safe_referer_or_root`` to reject attacker-controlled Referer values
    (cross-origin URLs) — otherwise this becomes a reflected open redirect
    accessible to any attacker who can trigger a form validation error."""
    request.session[SESSION_ERRORS_KEY] = errors
    return RedirectResponse(safe_referer_or_root(request), status_code=303)
