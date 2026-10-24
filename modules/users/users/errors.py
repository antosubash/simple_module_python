"""HTTP mapping of users domain errors."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from users.exceptions import AdminAccountSafetyError, AdminPermissionError, LoginLockedError


async def _admin_permission(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_403_FORBIDDEN)


async def _admin_safety(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)


async def _login_locked(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, LoginLockedError)
    return JSONResponse(
        {"detail": str(exc)},
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(exc.retry_after)},
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AdminPermissionError, _admin_permission)
    app.add_exception_handler(AdminAccountSafetyError, _admin_safety)
    app.add_exception_handler(LoginLockedError, _login_locked)
