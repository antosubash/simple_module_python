"""HTTP mapping of settings domain errors."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from settings._managed_keys import ManagedKeyError, ModuleKeyError
from settings.constants import STATUS_UNPROCESSABLE


async def _managed_key(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, ManagedKeyError)
    return JSONResponse(
        {"detail": str(exc), "clear_via": exc.clear_via}, status_code=STATUS_UNPROCESSABLE
    )


async def _module_key(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, ModuleKeyError)
    return JSONResponse(
        {"detail": str(exc), "edit_via": exc.edit_via}, status_code=STATUS_UNPROCESSABLE
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ManagedKeyError, _managed_key)
    app.add_exception_handler(ModuleKeyError, _module_key)
