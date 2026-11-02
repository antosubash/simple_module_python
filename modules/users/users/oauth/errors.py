"""Keep browser OAuth failures on the login page, with fixed public codes."""

from fastapi import HTTPException, Request
from starlette.responses import RedirectResponse

from users.constants import LOGIN_PAGE_PATH

OAUTH_ERROR_CODES = frozenset({"account_not_verified", "signup_disabled", "signin_failed"})

_PUBLIC_CODES = {
    "OAUTH_ACCOUNT_NOT_VERIFIED": "account_not_verified",
    "OAUTH_SIGNUP_DISABLED": "signup_disabled",
}


def _is_browser_navigation(request: Request) -> bool:
    # The callback is reached by the provider redirecting the browser back;
    # API and XHR callers keep the JSON error body.
    accept = request.headers.get("accept", "")
    return "text/html" in accept and request.headers.get("x-requested-with") != "XMLHttpRequest"


def refuse_login(request: Request, detail: str, status_code: int = 400) -> RedirectResponse:
    if not _is_browser_navigation(request):
        raise HTTPException(status_code=status_code, detail=detail)
    code = _PUBLIC_CODES.get(detail, "signin_failed")
    return RedirectResponse(f"{LOGIN_PAGE_PATH}?oauth_error={code}", status_code=303)
