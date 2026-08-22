"""Branding's ``design_pack`` — the site-wide look, chosen by an administrator.

The pack is a branding setting rather than a per-page property: one site has
one look, and the public page reads it from shared props. Branding owns the
*selection*; the packs available to select come from whichever modules
registered them at boot (``app.state.design_packs``).
"""

from __future__ import annotations

import httpx
import pytest
from branding.contracts.schemas import BrandingUpdate
from branding.settings import BrandingSettings
from branding.shared_props import branding_payload
from simple_module_core.design_packs import DesignPack

_GCA = DesignPack(value="gca", label="Canopy Atlas")


# ── Unit: settings validation ──────────────────────────────────────────


def test_defaults_to_no_pack() -> None:
    # "" means base tokens only — a site with no pack installed is the norm.
    assert BrandingSettings().design_pack == ""


def test_accepts_a_slug_shaped_value() -> None:
    assert BrandingSettings(design_pack="gca").design_pack == "gca"
    assert BrandingSettings(design_pack="canopy-atlas").design_pack == "canopy-atlas"


@pytest.mark.parametrize("bad", ["GCA", "canopy atlas", "-gca", "canopy_atlas"])
def test_rejects_a_value_that_is_not_a_css_class_fragment(bad: str) -> None:
    # The public root element carries f"{design_pack}-root"; anything that
    # isn't a bare lowercase identifier fragment can't select.
    with pytest.raises(ValueError):
        BrandingSettings(design_pack=bad)


def test_settings_validator_does_not_check_registration() -> None:
    # Shape only. Whether a module actually ships this pack is the endpoint's
    # job — settings are also hydrated from the DB at boot, where a pack whose
    # module was since uninstalled must not crash the app.
    assert BrandingSettings(design_pack="not-installed").design_pack == "not-installed"


# ── Unit: shared-props payload ─────────────────────────────────────────


def test_payload_reports_no_pack_as_none() -> None:
    assert branding_payload(BrandingSettings())["designPack"] is None


def test_payload_carries_the_selected_pack() -> None:
    payload = branding_payload(BrandingSettings(design_pack="gca"))
    assert payload["designPack"] == "gca"


# ── Unit: DTO ──────────────────────────────────────────────────────────


def test_update_dto_accepts_a_pack_and_a_clear() -> None:
    assert BrandingUpdate(design_pack="gca").design_pack == "gca"
    assert BrandingUpdate(design_pack="").design_pack == ""


def test_update_dto_rejects_a_bad_shape() -> None:
    with pytest.raises(ValueError):
        BrandingUpdate(design_pack="Not A Slug")


# ── Integration: API validates against the registry ────────────────────


async def test_update_accepts_a_registered_pack(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    app.state.design_packs.register(_GCA)

    resp = await authenticated_client.put("/api/branding/", json={"design_pack": "gca"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["design_pack"] == "gca"
    assert app.state.branding.settings.design_pack == "gca"


async def test_update_rejects_a_pack_no_module_provides(
    authenticated_client: httpx.AsyncClient,
) -> None:
    # Accepting it would put "aurora-root" on the document with no stylesheet
    # behind it — the site would look unchanged and nothing would say why.
    resp = await authenticated_client.put("/api/branding/", json={"design_pack": "aurora"})

    assert resp.status_code == 422, resp.text
    assert "aurora" in resp.text


async def test_update_allows_clearing_the_pack(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    app.state.design_packs.register(_GCA)
    await authenticated_client.put("/api/branding/", json={"design_pack": "gca"})

    resp = await authenticated_client.put("/api/branding/", json={"design_pack": ""})

    assert resp.status_code == 200, resp.text
    assert resp.json()["design_pack"] == ""
    assert app.state.branding.settings.design_pack == ""


async def test_a_pack_left_unmentioned_is_untouched(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    app.state.design_packs.register(_GCA)
    await authenticated_client.put("/api/branding/", json={"design_pack": "gca"})

    await authenticated_client.put("/api/branding/", json={"app_name": "Acme Corp"})

    assert app.state.branding.settings.design_pack == "gca"


# ── Integration: the view supplies the dropdown options ────────────────


async def test_manage_page_receives_the_registered_packs(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    app.state.design_packs.register(_GCA)

    page = await authenticated_client.get("/admin/branding/", follow_redirects=False)

    assert page.status_code == 200, page.text
    # Inertia serialises page props into the shell's data-page attribute.
    assert "designPacks" in page.text
    assert "Canopy Atlas" in page.text
