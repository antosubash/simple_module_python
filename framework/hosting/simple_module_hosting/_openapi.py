"""OpenAPI export plumbing (#456).

Three small pieces, kept apart from ``create_app``:

* ``make_unique_id_function`` — stable ``<module>_<function>`` operationIds, so
  generated clients get method names like ``users_list_users`` instead of
  ``list_users_api_users__get``.
* ``install_openapi_filter`` — the published schema is the JSON API only. View
  routes are already ``include_in_schema=False``; this also drops any other
  non-``/api/`` path (host routes, health) so a client generator never sees them.
* ``API_OPENAPI_URL`` / ``openapi_served`` — where and when it is served.
"""

from __future__ import annotations

import logging
import re
import warnings
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.routing import APIRoute

__all__ = [
    "API_OPENAPI_URL",
    "dedupe_operation_ids",
    "install_openapi_filter",
    "make_unique_id_function",
    "openapi_served",
]

logger = logging.getLogger(__name__)

API_OPENAPI_URL = "/api/openapi.json"
_API_PREFIX = "/api/"


def openapi_served(*, is_development: bool, openapi_public: bool) -> bool:
    """Always in development; elsewhere only when the operator opted in."""
    return is_development or openapi_public


def _snake(name: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", spaced).strip("_").lower()


def make_unique_id_function() -> Callable[[APIRoute], str]:
    """Build an operationId generator: ``<module>_<endpoint function name>``.

    The module is the route's first tag (``wire_module_routes`` tags each API
    router with the module name). Stateless on purpose: FastAPI calls it again
    when a router is included, so any bookkeeping here would see every route
    twice. Clashes are resolved on the finished schema by ``dedupe_operation_ids``.
    """

    def unique_id(route: APIRoute) -> str:
        module = _snake(route.tags[0]) if route.tags and isinstance(route.tags[0], str) else ""
        return f"{module}_{route.name}" if module else route.name

    return unique_id


def dedupe_operation_ids(schema: dict) -> None:
    """Make every ``operationId`` unique, appending method and path on a clash."""
    seen: set[str] = set()
    for path, item in schema.get("paths", {}).items():
        for method, op in item.items():
            if not isinstance(op, dict) or "operationId" not in op:
                continue
            base = op["operationId"]
            if base in seen:
                op["operationId"] = f"{base}_{method}_{_snake(path)}"
                logger.warning(
                    "Duplicate OpenAPI operationId %r; using %r", base, op["operationId"]
                )
            seen.add(op["operationId"])


def install_openapi_filter(app: FastAPI) -> None:
    """Make ``app.openapi()`` list only ``/api/`` paths."""
    original = app.openapi

    def openapi() -> dict:
        if app.openapi_schema is None:
            # FastAPI warns about duplicate ids as it builds; they are resolved
            # (and logged once) by dedupe_operation_ids below.
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Duplicate Operation ID")
                schema = original()
            schema["paths"] = {
                p: v for p, v in schema.get("paths", {}).items() if p.startswith(_API_PREFIX)
            }
            dedupe_operation_ids(schema)
        assert app.openapi_schema is not None
        return app.openapi_schema

    app.openapi = openapi
