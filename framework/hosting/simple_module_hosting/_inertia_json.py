"""Make Inertia's JSON branch encode props the way its HTML branch does.

``fastapi-inertia`` renders the same props two ways and configures only one of
them::

    # full page load — honours InertiaConfig.json_encoder
    json_string = json.dumps(page_data, cls=self._config.json_encoder)

    # client-side visit — Starlette's JSONResponse, so plain json.dumps
    return JSONResponse(content=await self._get_page_data(), ...)

``InertiaJsonEncoder`` exists precisely to run the payload through FastAPI's
``jsonable_encoder``, and the second branch never reaches it. The effect is a
route that works on a reload and 500s on every client-side visit, for any prop
the stdlib encoder cannot handle — ``Path``, ``Decimal``, ``UUID``, a dataclass,
an enum.

Settings → Modules is where this surfaced: it reflects each installed module's
pydantic settings back to the admin, and a module whose settings carry a
``Path`` field (``PagebuilderSettings.media_root``) puts a ``PosixPath`` in the
payload::

    TypeError: Object of type PosixPath is not JSON serializable

Fixing it here rather than in each module is deliberate. A module putting a
rich value in props is not doing anything wrong — the HTML branch has always
accepted it — so the asymmetry is the defect, and closing it at the point of
serialisation covers every module and every prop type at once.

Applied by wrapping the dependency published on ``app.state.inertia_dependency``,
which ``inertia_deps.get_inertia`` calls once per request. The replacement binds
to the instance, so the library's class is untouched and any other construction
path keeps the stock behaviour.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

#: The headers upstream's ``_render_json`` sets, reproduced so the wrap is a
#: pure encoder change. ``InertiaCacheMiddleware`` owns the caching rules and
#: extends ``Vary`` on the way out.
_JSON_HEADERS = {"X-Inertia": "true", "Vary": "Accept"}


def json_safe_inertia_dependency(inertia_dep: Any) -> Any:
    """Wrap an Inertia dependency so its JSON branch uses ``jsonable_encoder``.

    The wrapped callable keeps the ``(request, client)`` shape
    ``inertia_dependency_factory`` returns. An instance that doesn't expose the
    private hook this relies on is handed back untouched: the failure mode is
    the 500 that already happens, and refusing to boot because an upstream
    attribute moved would be a worse trade.
    """

    def dependency(request: Any, client: Any = None) -> Any:
        inertia = inertia_dep(request, client)
        if hasattr(inertia, "_get_page_data"):
            inertia._render_json = _render_json_for(inertia)
        else:  # pragma: no cover - upstream layout changed
            logger.warning(
                "Inertia instance has no _get_page_data; JSON responses keep the "
                "stock encoder and non-JSON-native props will fail to serialise"
            )
        return inertia

    return dependency


def _render_json_for(inertia: Any) -> Any:
    """Build the instance's replacement ``_render_json``."""

    async def _render_json() -> JSONResponse:
        page_data = await inertia._get_page_data()
        return JSONResponse(content=jsonable_encoder(page_data), headers=_JSON_HEADERS)

    return _render_json


__all__ = ["json_safe_inertia_dependency"]
