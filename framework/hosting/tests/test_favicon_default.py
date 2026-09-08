"""The generated favicon an install has before anyone uploads one.

Emitted as a data URI straight into a ``href="…"`` attribute, so the encoding
is the whole risk: a surviving ``#`` truncates the URI at the gradient
reference and the mark loses its fill, and a surviving ``"`` ends the attribute.
"""

from __future__ import annotations

from urllib.parse import unquote

import pytest
from simple_module_hosting._favicon import default_favicon_data_uri

_PREFIX = "data:image/svg+xml,"


def _svg(uri: str) -> str:
    return unquote(uri.removeprefix(_PREFIX))


class TestEncoding:
    def test_it_is_an_svg_data_uri(self) -> None:
        assert default_favicon_data_uri("SimpleModule").startswith(_PREFIX)

    @pytest.mark.parametrize("char", ["#", '"', "<", ">", " "])
    def test_no_uri_breaking_character_survives_encoding(self, char: str) -> None:
        payload = default_favicon_data_uri("SimpleModule").removeprefix(_PREFIX)
        assert char not in payload

    def test_the_payload_decodes_to_well_formed_svg(self) -> None:
        svg = _svg(default_favicon_data_uri("SimpleModule"))
        assert svg.startswith("<svg ") and svg.endswith("</svg>")
        # The gradient is referenced by the id it defines; a mismatch here is
        # an unfilled square that still "renders".
        assert 'id="a"' in svg and "url(#a)" in svg


class TestTheMark:
    @pytest.mark.parametrize(
        ("app_name", "initial"),
        [("SimpleModule", "S"), ("Acme Corp", "A"), ("  spaced", "S"), ("zephyr", "Z")],
    )
    def test_it_shows_the_app_initial(self, app_name: str, initial: str) -> None:
        """Mirrors BrandingMark's badge, so tab and sidebar never disagree."""
        assert f">{initial}</text>" in _svg(default_favicon_data_uri(app_name))

    @pytest.mark.parametrize("app_name", ["", "   "])
    def test_a_nameless_app_still_gets_a_mark(self, app_name: str) -> None:
        assert ">S</text>" in _svg(default_favicon_data_uri(app_name))

    def test_an_app_name_cannot_inject_markup(self) -> None:
        svg = _svg(default_favicon_data_uri("<script>"))
        assert ">&lt;</text>" in svg
        assert "<script>" not in svg


class TestBrandColour:
    def test_the_default_uses_the_brand_gradient(self) -> None:
        svg = _svg(default_favicon_data_uri("SimpleModule"))
        assert "#00955c" in svg and "#005c4a" in svg

    def test_a_configured_colour_replaces_both_stops(self) -> None:
        svg = _svg(default_favicon_data_uri("Acme", "#1a7dd1"))
        assert svg.count("#1a7dd1") == 2
        assert "#00955c" not in svg

    @pytest.mark.parametrize("bogus", ["red", "1a7dd1", "#12", "#xyzxyz", "'; --", ""])
    def test_a_non_hex_colour_is_ignored_rather_than_interpolated(self, bogus: str) -> None:
        svg = _svg(default_favicon_data_uri("Acme", bogus))
        assert "#00955c" in svg
        assert bogus not in svg or bogus == ""
