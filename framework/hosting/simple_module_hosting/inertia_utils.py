"""Shared Inertia utilities for form-action view endpoints."""

from __future__ import annotations

from fastapi import Request
from pydantic import ValidationError
from simple_module_inertia import errors_from_validation
from starlette.responses import RedirectResponse

from simple_module_hosting.redirects import safe_referer_or_root

SESSION_ERRORS_KEY = "_errors"


def validation_errors_to_dict(exc: ValidationError) -> dict[str, str]:
    """Return the first validation message for each top-level form field."""
    return errors_from_validation(exc.errors())


def redirect_back_with_errors(request: Request, errors: dict[str, str]) -> RedirectResponse:
    """Store validation errors in the session and redirect to the referring page.

    Uses ``safe_referer_or_root`` to reject attacker-controlled Referer values
    (cross-origin URLs) — otherwise this becomes a reflected open redirect
    accessible to any attacker who can trigger a form validation error."""
    bag = request.headers.get("X-Inertia-Error-Bag")
    request.session[SESSION_ERRORS_KEY] = errors if bag is None else {bag: errors}
    return RedirectResponse(safe_referer_or_root(request), status_code=303)
