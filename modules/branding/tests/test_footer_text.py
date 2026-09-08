"""Admin-configurable footer text.

The footer's copyright line was a framework constant — ``© {year} · MIT`` —
so every deployment advertised the framework's licence as its own. The links
became configurable in #282; this is the line beside them.
"""

from __future__ import annotations

import pytest
from branding.constants import MAX_FOOTER_TEXT_LEN
from branding.contracts.schemas import BrandingUpdate
from branding.settings import BrandingSettings
from branding.shared_props import branding_payload
from httpx import AsyncClient
from pydantic import ValidationError

_TEXT = "© 2026 Acme Corp"


class TestSettings:
    def test_unset_is_blank_so_the_framework_caption_stands(self) -> None:
        assert BrandingSettings().footer_text == ""

    def test_the_text_is_trimmed(self) -> None:
        assert BrandingSettings(footer_text=f"  {_TEXT}  ").footer_text == _TEXT

    def test_too_long_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at most"):
            BrandingSettings(footer_text="x" * (MAX_FOOTER_TEXT_LEN + 1))

    def test_control_characters_are_rejected(self) -> None:
        # The caption lands in HTML and in transactional email headers.
        with pytest.raises(ValidationError, match="control characters"):
            BrandingSettings(footer_text="Acme\nCorp")


class TestUpdateDto:
    def test_it_accepts_and_trims(self) -> None:
        assert BrandingUpdate(footer_text=f" {_TEXT} ").footer_text == _TEXT

    def test_blank_clears_the_override(self) -> None:
        assert BrandingUpdate(footer_text="").footer_text == ""

    def test_too_long_is_a_422_not_a_500(self) -> None:
        with pytest.raises(ValidationError, match="at most"):
            BrandingUpdate(footer_text="x" * (MAX_FOOTER_TEXT_LEN + 1))


class TestSharedProp:
    def test_unset_is_none_so_the_frontend_falls_back(self) -> None:
        assert branding_payload(BrandingSettings())["footerText"] is None

    def test_a_set_text_reaches_the_frontend(self) -> None:
        payload = branding_payload(BrandingSettings(footer_text=_TEXT))
        assert payload["footerText"] == _TEXT


class TestApi:
    async def test_put_round_trips_the_text(self, app, authenticated_client: AsyncClient) -> None:
        resp = await authenticated_client.put("/api/branding/", json={"footer_text": _TEXT})

        assert resp.status_code == 200, resp.text
        assert resp.json()["footer_text"] == _TEXT
        assert app.state.branding.settings.footer_text == _TEXT

    async def test_the_text_is_cleared_by_sending_blank(
        self, app, authenticated_client: AsyncClient
    ) -> None:
        await authenticated_client.put("/api/branding/", json={"footer_text": _TEXT})

        resp = await authenticated_client.put("/api/branding/", json={"footer_text": ""})

        assert resp.status_code == 200, resp.text
        assert resp.json()["footer_text"] == ""
        assert app.state.branding.settings.footer_text == ""

    async def test_publishing_the_text_leaves_the_links_alone(
        self, authenticated_client: AsyncClient
    ) -> None:
        await authenticated_client.put(
            "/api/branding/",
            json={"footer_links": [{"label": "Privacy", "href": "/privacy"}]},
        )

        resp = await authenticated_client.put("/api/branding/", json={"footer_text": _TEXT})

        assert [link["label"] for link in resp.json()["footer_links"]] == ["Privacy"]

    async def test_an_over_long_text_is_rejected(self, authenticated_client: AsyncClient) -> None:
        resp = await authenticated_client.put(
            "/api/branding/", json={"footer_text": "x" * (MAX_FOOTER_TEXT_LEN + 1)}
        )

        assert resp.status_code == 422, resp.text
