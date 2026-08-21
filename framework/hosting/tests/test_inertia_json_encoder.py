"""Both Inertia render paths must encode props the same way.

Upstream configures ``InertiaConfig.json_encoder`` — which exists to run props
through FastAPI's ``jsonable_encoder`` — and then only applies it on the full
page load. A client-side visit builds a Starlette ``JSONResponse``, reaching
plain ``json.dumps``. Any prop the stdlib cannot encode therefore renders on a
reload and 500s when reached by clicking a link, which is a miserable bug to
read from a stack trace: the page "works", right up until it is navigated to.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from simple_module_hosting._inertia_json import json_safe_inertia_dependency
from starlette.responses import JSONResponse

_OK = 200


class _FakeInertia:
    """Stands in for the library's Inertia, with the two hooks the wrap uses."""

    def __init__(self, page_data: dict) -> None:
        self._page_data = page_data
        self.rendered_by_stock_encoder = False

    async def _get_page_data(self) -> dict:
        return self._page_data

    async def _render_json(self) -> JSONResponse:
        # What upstream does: no encoder, so a rich value raises here.
        self.rendered_by_stock_encoder = True
        return JSONResponse(content=self._page_data)


def _dependency_for(page_data: dict):
    inertia = _FakeInertia(page_data)
    dependency = json_safe_inertia_dependency(lambda request, client=None: inertia)
    return dependency(object(), None)


class TestJsonSafeRendering:
    async def test_a_path_prop_would_break_the_stock_encoder(self) -> None:
        """Establishes the bug this wrap exists for, so the fix can't drift."""
        with pytest.raises(TypeError, match="PosixPath"):
            json.dumps({"props": {"media_root": Path("var/media")}})

    async def test_a_path_prop_renders(self) -> None:
        inertia = _dependency_for({"props": {"media_root": Path("var/media")}})

        response = await inertia._render_json()

        assert response.status_code == _OK
        assert json.loads(bytes(response.body))["props"]["media_root"] == "var/media"

    async def test_the_wrap_replaces_the_stock_path(self) -> None:
        """Not merely catching the error afterwards — the encoder is swapped."""
        inertia = _dependency_for({"props": {}})

        await inertia._render_json()

        assert inertia.rendered_by_stock_encoder is False

    async def test_inertia_headers_are_preserved(self) -> None:
        inertia = _dependency_for({"props": {}})

        response = await inertia._render_json()

        assert response.headers["x-inertia"] == "true"

    async def test_an_unfamiliar_instance_is_left_alone(self) -> None:
        """An upstream rename must not take the boot down with it."""

        class _Unfamiliar:
            pass

        original = _Unfamiliar()
        wrapped = json_safe_inertia_dependency(lambda request, client=None: original)

        assert wrapped(object(), None) is original
