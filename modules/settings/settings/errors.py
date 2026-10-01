"""HTTP mapping of settings domain errors."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from settings._managed_keys import ManagedKeyError
from settings.constants import STATUS_UNPROCESSABLE


async def _managed_key(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, ManagedKeyError)
    return JSONResponse(
        {"detail": str(exc), "clear_via": exc.clear_via}, status_code=STATUS_UNPROCESSABLE
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ManagedKeyError, _managed_key)
