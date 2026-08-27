"""Admin-configurable footer links — GH #282.

Until 0.0.32 the footer's links were a module-level constant in
``@simple-module-py/ui``, so every deployment advertised the framework
author's repository under "Docs", "Changelog" and "GitHub" on every page,
with no setting, prop or admin screen that changed it.
"""

from __future__ import annotations

import pytest
from branding.constants import MAX_FOOTER_LINKS
from branding.contracts.schemas import BrandingUpdate, FooterLink
from branding.settings import BrandingSettings
from branding.shared_props import branding_payload
from httpx import AsyncClient
from pydantic import ValidationError

_LINKS = [
    {"label": "Docs", "href": "https://example.org/docs"},
    {"label": "Contact", "href": "mailto:team@example.org"},
    {"label": "About", "href": "/about"},
]


class TestSettings:
    def test_unset_is_empty_so_the_framework_links_stand(self) -> None:
        assert BrandingSettings().footer_links == []

    def test_links_hydrate_from_plain_dicts(self) -> None:
        """The settings store round-trips this field as JSON."""
        settings = BrandingSettings(footer_links=_LINKS)

        assert [link.label for link in settings.footer_links] == ["Docs", "Contact", "About"]
        assert settings.footer_links[2].href == "/about"

    def test_too_many_links_are_rejected(self) -> None:
        too_many = [{"label": f"L{i}", "href": "/x"} for i in range(MAX_FOOTER_LINKS + 1)]

        with pytest.raises(ValidationError, match="at most"):
            BrandingSettings(footer_links=too_many)

    def test_blank_label_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not be blank"):
            BrandingSettings(footer_links=[{"label": "   ", "href": "/x"}])


class TestHrefAllowList:
    """The href lands in an ``<a href>`` on every page, signed-in or not."""

    @pytest.mark.parametrize(
        "href",
        [
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "  javascript:alert(1)",
            "data:text/html;base64,PHNjcmlwdD4=",
            "vbscript:msgbox(1)",
            "//evil.example.com",
        ],
    )
    def test_dangerous_or_offsite_schemes_are_rejected(self, href: str) -> None:
        with pytest.raises(ValidationError):
            FooterLink(label="Click", href=href)

    @pytest.mark.parametrize(
        "href",
        [
            "https://example.org",
            "http://example.org/a/b?c=d#e",
            "mailto:team@example.org",
            "/about",
            "/a/deep/path?q=1",
        ],
    )
    def test_allowed_targets_survive(self, href: str) -> None:
        assert FooterLink(label="Link", href=href).href == href

    @pytest.mark.parametrize(
        "href",
        [
            "/\\evil.example.com",
            "/\\\\evil.example.com",
            "https://ok.example.org/a\\b",
        ],
    )
    def test_backslashes_are_rejected(self, href: str) -> None:
        """A browser reads `/\\host` as `//host` — the bypass the `//` rule closes."""
        with pytest.raises(ValidationError, match="backslash"):
            FooterLink(label="Click", href=href)

    def test_percent_encoded_backslash_is_still_a_path(self) -> None:
        """`%5C` is decoded after the authority is parsed, so it stays relative."""
        assert FooterLink(label="Link", href="/%5Cfile").href == "/%5Cfile"

    def test_control_characters_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="control characters"):
            FooterLink(label="Link", href="https://example.org\nX")


class TestSharedProp:
    def test_unset_sends_none_so_the_frontend_falls_back(self) -> None:
        assert branding_payload(BrandingSettings())["footerLinks"] is None

    def test_set_links_reach_the_frontend_in_order(self) -> None:
        payload = branding_payload(BrandingSettings(footer_links=_LINKS))

        assert payload["footerLinks"] == _LINKS


class TestUpdateDto:
    def test_omitting_the_field_leaves_links_alone(self) -> None:
        """A PUT that only changes the app name must not wipe the footer."""
        data = BrandingUpdate(app_name="Acme")

        assert "footer_links" not in data.model_dump(exclude_unset=True)

    def test_dumps_to_plain_dicts_for_the_settings_store(self) -> None:
        """``apply_changes_and_reload`` json.dumps() whatever it's handed."""
        data = BrandingUpdate(footer_links=_LINKS)

        assert data.model_dump(exclude_unset=True)["footer_links"] == _LINKS

    def test_empty_list_is_a_real_value_not_an_omission(self) -> None:
        """Clearing back to the framework defaults has to be expressible."""
        data = BrandingUpdate(footer_links=[])

        assert data.model_dump(exclude_unset=True)["footer_links"] == []


class TestApi:
    async def test_put_persists_and_reaches_the_shared_props(
        self, authenticated_client: AsyncClient
    ) -> None:
        res = await authenticated_client.put("/api/branding/", json={"footer_links": _LINKS})
        assert res.status_code == 200, res.text
        assert res.json()["footer_links"] == _LINKS

        page = await authenticated_client.get("/admin/branding/", headers={"X-Inertia": "true"})
        assert page.json()["props"]["branding"]["footerLinks"] == _LINKS

    async def test_put_rejects_a_javascript_href(self, authenticated_client: AsyncClient) -> None:
        res = await authenticated_client.put(
            "/api/branding/",
            json={"footer_links": [{"label": "Click", "href": "javascript:alert(1)"}]},
        )

        assert res.status_code == 422

    async def test_clearing_restores_the_framework_links(
        self, authenticated_client: AsyncClient
    ) -> None:
        await authenticated_client.put("/api/branding/", json={"footer_links": _LINKS})

        res = await authenticated_client.put("/api/branding/", json={"footer_links": []})

        assert res.status_code == 200, res.text
        assert res.json()["footer_links"] == []

    async def test_anonymous_visitors_get_the_links_too(
        self, authenticated_client: AsyncClient, client: AsyncClient
    ) -> None:
        """The footer renders on the public shell, where nobody is signed in."""
        await authenticated_client.put("/api/branding/", json={"footer_links": _LINKS})

        page = await client.get("/", headers={"X-Inertia": "true"})

        assert page.json()["props"]["branding"]["footerLinks"] == _LINKS
