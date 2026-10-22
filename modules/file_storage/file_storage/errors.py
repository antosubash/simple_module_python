"""HTTP mapping for unavailable stored-file providers."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from simple_module_hosting.i18n_deps import get_translator

from file_storage import constants
from file_storage.backend_guard import BackendUnavailableError


async def _backend_unavailable(request: Request, exc: Exception) -> JSONResponse:
    translator = await get_translator(request)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": {
                "code": constants.ErrorCode.BACKEND_UNAVAILABLE,
                "message": translator.t(constants.I18nKey.ERR_BACKEND_UNAVAILABLE),
            }
        },
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BackendUnavailableError, _backend_unavailable)
