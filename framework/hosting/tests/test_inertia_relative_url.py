"""Inertia's page ``url`` must be root-relative, not absolute.

Upstream emits ``str(request.url)``. Behind a TLS-terminating reverse proxy the
container sees http while the browser is on https, so the client's
``history.pushState`` is handed a cross-origin url and the browser refuses it —
a ``SecurityError`` on every single page, and history state that is never
written. The protocol asks for ``"url": "/events/80"`` precisely so this cannot
happen.
"""

from __future__ import annotations

import json

import pytest
from simple_module_hosting._inertia_json import json_safe_inertia_dependency
from simple_module_hosting._inertia_url import (
    relative_page_url_dependency,
    to_relative_url,
)


class _FakeInertia:
    """Stands in for the library's Inertia, with the hook the wrap patches."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def _get_page_data(self) -> dict:
        return {
            "component": "Dashboard/Home",
            "props": {"greeting": "hi"},
            "url": self._url,
            "version": "1.0",
        }


def _inertia_for(url: str):
    inertia = _FakeInertia(url)
    dependency = relative_page_url_dependency(lambda request, client=None: inertia)
    return dependency(object(), None)


class TestToRelativeUrl:
    @pytest.mark.parametrize(
        ("absolute", "expected"),
        [
            ("http://py.simplemodule.dev/", "/"),
            ("https://py.simplemodule.dev/dashboard/", "/dashboard/"),
            ("http://host:8000/admin/users/", "/admin/users/"),
            ("http://host:8000/files?q=logo&page=2", "/files?q=logo&page=2"),
            # No path at all still has to name one — "" is not a valid url.
            ("http://host:8000", "/"),
        ],
    )
    def test_an_absolute_url_keeps_only_path_and_query(self, absolute: str, expected: str) -> None:
        assert to_relative_url(absolute) == expected

    @pytest.mark.parametrize(
        "already_relative",
        ["/", "/dashboard/", "/files?q=logo"],
    )
    def test_a_relative_url_is_unchanged(self, already_relative: str) -> None:
        """Idempotent, so double-wrapping and a future upstream fix are safe."""
        assert to_relative_url(already_relative) == already_relative

    def test_the_fragment_is_not_invented(self) -> None:
        """Fragments never reach the server; none should appear in the payload."""
        assert to_relative_url("https://host/page#section") == "/page"


class TestRelativePageUrlDependency:
    async def test_the_page_url_is_relative(self) -> None:
        inertia = _inertia_for("http://py.simplemodule.dev/dashboard/")

        page_data = await inertia._get_page_data()

        assert page_data["url"] == "/dashboard/"

    async def test_the_rest_of_the_payload_is_untouched(self) -> None:
        inertia = _inertia_for("https://py.simplemodule.dev/dashboard/?tab=1")

        page_data = await inertia._get_page_data()

        assert page_data["component"] == "Dashboard/Home"
        assert page_data["props"] == {"greeting": "hi"}
        assert page_data["version"] == "1.0"
        assert page_data["url"] == "/dashboard/?tab=1"

    async def test_a_cross_scheme_url_can_never_reach_the_client(self) -> None:
        """The exact shape that made pushState throw on every deployed page."""
        inertia = _inertia_for("http://py.simplemodule.dev/admin/settings/")

        page_data = await inertia._get_page_data()

        assert not page_data["url"].startswith("http://")
        assert not page_data["url"].startswith("https://")

    async def test_it_composes_with_the_json_wrap(self) -> None:
        """Both wraps are applied in production; neither may undo the other."""
        inertia = _FakeInertia("http://py.simplemodule.dev/files?q=logo")
        dependency = relative_page_url_dependency(
            json_safe_inertia_dependency(lambda request, client=None: inertia)
        )
        wrapped = dependency(object(), None)

        response = await wrapped._render_json()

        assert json.loads(bytes(response.body))["url"] == "/files?q=logo"

    async def test_an_unpatchable_instance_is_handed_back(self) -> None:
        """Upstream moving the hook must not stop the app from booting."""

        class _Foreign:
            pass

        foreign = _Foreign()
        dependency = relative_page_url_dependency(lambda request, client=None: foreign)

        assert dependency(object(), None) is foreign
