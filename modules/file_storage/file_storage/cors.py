"""CORS for anonymous public-file reads (#527).

Any origin may read a public file, never with credentials. Range-capable, so a
cross-origin ``<video>`` or PDF viewer can seek. The ``public_files_cors`` module
setting is read on every request, so flipping it needs no restart.

With the S3 backend a read may redirect to a presigned bucket URL; the browser
then applies the *bucket's* CORS configuration, which this policy cannot set.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from simple_module_core.cors import WILDCARD, CorsPolicy, CorsPolicyRegistry

from file_storage import constants
from file_storage.cookieless import PUBLIC_PATH_PATTERN

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_public_files_cors(
    registry: CorsPolicyRegistry, get_app: Callable[[], FastAPI | None]
) -> None:
    def enabled() -> bool:
        app = get_app()
        services = getattr(getattr(app, "state", None), constants.MODULE_NAME, None)
        return services is not None and services.settings.public_files_cors

    registry.add_regex(
        PUBLIC_PATH_PATTERN,
        CorsPolicy(
            origins=(WILDCARD,),
            allow_credentials=False,
            methods=constants.PUBLIC_CORS_METHODS,
            headers=constants.PUBLIC_CORS_ALLOW_HEADERS,
            expose_headers=constants.PUBLIC_CORS_EXPOSE_HEADERS,
        ),
        enabled=enabled,
    )
