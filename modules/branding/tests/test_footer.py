"""Configurable multi-column footer.

Ported from IIASA.GeoWiki's ``FooterAppService`` — same shape (brand text,
columns of links, a social row), same limits, and the same ``ValidateHref``
allow-list. That last one is the security-relevant part: these URLs are
authored by an admin and rendered into an anchor on every page, guest pages
included, so anything but http(s) or an in-app path has to be refused.
"""

from __future__ import annotations

import httpx
import pytest
from branding.contracts.footer import FooterColumn, FooterConfig, FooterLink
from branding.footer import (
    MAX_COLUMNS,
    MAX_LINKS_PER_COLUMN,
    MAX_SERIALISED_LEN,
    MAX_SOCIAL_LINKS,
    dumps,
    loads,
    validate_href,
)
from branding.settings import BrandingSettings
from branding.shared_props import footer_payload

# ── Unit: href allow-list ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "href",
    ["/pricing", "/", "https://example.com", "http://example.com/x?y=1#z"],
)
def test_accepts_app_paths_and_http_urls(href: str) -> None:
    assert validate_href(href) == href


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "  javascript:alert(1)  ",
        "data:text/html;base64,PHNjcmlwdD4=",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
    ],
)
def test_rejects_every_scheme_that_is_not_http(href: str) -> None:
    # A javascript: href in the footer would execute on every page load.
    with pytest.raises(ValueError):
        validate_href(href)


def test_rejects_a_protocol_relative_url() -> None:
    # "//evil.com" reads like a path but is an absolute URL to another origin.
    with pytest.raises(ValueError):
        validate_href("//evil.com/phish")


def test_rejects_an_empty_href() -> None:
    with pytest.raises(ValueError):
        validate_href("   ")


def test_trims_surrounding_whitespace() -> None:
    assert validate_href("  /pricing  ") == "/pricing"


# ── Unit: (de)serialisation is lenient on read, bounded on write ───────


@pytest.mark.parametrize("raw", ["", "   ", "not json", "{}", "null", '["a", 1]'])
def test_unusable_stored_json_reads_as_an_empty_footer(raw: str) -> None:
    # Settings hydrate from the DB; a mangled row must not break every render.
    assert loads(raw) == []


def test_round_trips_a_structure() -> None:
    items = [{"title": "Product", "links": [{"label": "Pricing", "href": "/pricing"}]}]
    assert loads(dumps(items)) == items


def test_refuses_to_store_an_oversized_structure() -> None:
    with pytest.raises(ValueError, match="too large"):
        dumps([{"label": "x" * MAX_SERIALISED_LEN, "href": "/x"}])


# ── Unit: DTO limits ───────────────────────────────────────────────────


def test_rejects_too_many_columns() -> None:
    columns = [FooterColumn(title=f"C{i}", links=[]) for i in range(MAX_COLUMNS + 1)]
    with pytest.raises(ValueError):
        FooterConfig(columns=columns)


def test_rejects_too_many_links_in_one_column() -> None:
    links = [FooterLink(label=f"L{i}", href="/x") for i in range(MAX_LINKS_PER_COLUMN + 1)]
    with pytest.raises(ValueError):
        FooterColumn(title="Too many", links=links)


def test_rejects_too_many_social_links() -> None:
    links = [FooterLink(label=f"S{i}", href="/x") for i in range(MAX_SOCIAL_LINKS + 1)]
    with pytest.raises(ValueError):
        FooterConfig(social_links=links)


def test_rejects_a_blank_label() -> None:
    with pytest.raises(ValueError):
        FooterLink(label="   ", href="/x")


# ── Unit: shared-props payload ─────────────────────────────────────────


def test_payload_is_none_when_nothing_is_configured() -> None:
    # None keeps the framework's built-in footer, so untouched sites are as-is.
    assert footer_payload(BrandingSettings()) is None


def test_payload_appears_once_a_column_exists() -> None:
    settings = BrandingSettings(
        footer_columns=dumps([{"title": "Product", "links": [{"label": "P", "href": "/p"}]}])
    )
    payload = footer_payload(settings)
    assert payload is not None
    assert payload["columns"][0]["title"] == "Product"


# ── Integration ────────────────────────────────────────────────────────


_CONFIG = {
    "tagline": "Maps for everyone",
    "copyright_owner": "Acme Corp",
    "note": "Built on SimpleModule",
    "columns": [
        {"title": "Product", "links": [{"label": "Pricing", "href": "/pricing"}]},
        {"title": "Company", "links": [{"label": "About", "href": "https://acme.test/about"}]},
    ],
    "social_links": [{"label": "GitHub", "href": "https://github.com/acme"}],
}


async def test_saving_a_footer_persists_and_reads_back(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    resp = await authenticated_client.put("/api/branding/footer", json=_CONFIG)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["copyright_owner"] == "Acme Corp"
    assert [c["title"] for c in body["columns"]] == ["Product", "Company"]

    again = await authenticated_client.get("/api/branding/footer")
    assert again.json()["columns"][0]["links"][0]["href"] == "/pricing"


async def test_a_saved_footer_reaches_the_shared_props(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    await authenticated_client.put("/api/branding/footer", json=_CONFIG)

    from branding.shared_props import branding_payload

    payload = branding_payload(app.state.branding.settings)
    assert payload["footer"]["socialLinks"][0]["label"] == "GitHub"


async def test_the_api_rejects_a_javascript_link(
    authenticated_client: httpx.AsyncClient,
) -> None:
    bad = {
        **_CONFIG,
        "columns": [
            {"title": "Evil", "links": [{"label": "Click", "href": "javascript:alert(1)"}]}
        ],
    }

    resp = await authenticated_client.put("/api/branding/footer", json=bad)

    assert resp.status_code == 422, resp.text


async def test_saving_a_footer_replaces_rather_than_merges(
    authenticated_client: httpx.AsyncClient,
) -> None:
    await authenticated_client.put("/api/branding/footer", json=_CONFIG)

    resp = await authenticated_client.put(
        "/api/branding/footer",
        json={
            "tagline": "",
            "copyright_owner": "Acme",
            "note": "",
            "columns": [],
            "social_links": [],
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["columns"] == []


async def test_the_footer_requires_the_manage_permission(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/branding/footer")).status_code in (401, 403)
    assert (await client.put("/api/branding/footer", json=_CONFIG)).status_code in (401, 403)


async def test_the_footer_reaches_a_logged_out_visitor(
    client: httpx.AsyncClient, authenticated_client: httpx.AsyncClient
) -> None:
    # The public marketing page renders it, and that page is guest-facing.
    await authenticated_client.put("/api/branding/footer", json=_CONFIG)

    page = await client.get("/users/login", follow_redirects=False)

    assert page.status_code == 200, page.status_code
    assert "Maps for everyone" in page.text
