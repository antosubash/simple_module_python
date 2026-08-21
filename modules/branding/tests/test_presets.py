"""One-click branding presets.

Ported from IIASA.GeoWiki's ``BrandingPresets`` + ``ApplyPresetAsync``, with one
deliberate narrowing: GeoWiki presets set brand name and tagline because each
preset *is* a tenant, whereas here a preset is only a look. Overwriting the app
name or a freshly uploaded logo would destroy the work this page exists to do.
"""

from __future__ import annotations

import httpx
import pytest
from branding.presets import BUILTIN_PRESETS, PRESET_FIELDS, BrandingPreset, find_preset

# ── Unit: definitions ──────────────────────────────────────────────────


def test_presets_ship_and_have_unique_keys() -> None:
    keys = [p.key for p in BUILTIN_PRESETS]
    assert len(keys) == len(set(keys)), f"duplicate preset keys: {keys}"
    assert keys, "at least one built-in preset must ship"


def test_every_preset_only_touches_appearance() -> None:
    # The guard that keeps a preset from clobbering deployment identity.
    for preset in BUILTIN_PRESETS:
        assert set(preset.values) <= PRESET_FIELDS, preset.key


def test_every_preset_sets_a_valid_hex_colour() -> None:
    from branding.constants import HEX_COLOR_RE

    for preset in BUILTIN_PRESETS:
        colour = preset.values.get("primary_color")
        assert colour and HEX_COLOR_RE.match(colour), preset.key


def test_a_preset_cannot_declare_a_non_preset_field() -> None:
    # Catches a future preset that tries to smuggle in an identity field.
    with pytest.raises(ValueError, match="app_name"):
        BrandingPreset("bad", "Bad", {"app_name": "Acme"})


def test_swatch_exposes_the_colour_for_the_picker() -> None:
    assert BrandingPreset("x", "X", {"primary_color": "#123456"}).swatch == "#123456"
    assert BrandingPreset("y", "Y").swatch is None


def test_find_preset_misses_cleanly() -> None:
    assert find_preset(BUILTIN_PRESETS[0].key) is BUILTIN_PRESETS[0]
    assert find_preset("nope") is None


# ── Integration: applying ──────────────────────────────────────────────


async def test_applying_a_preset_changes_the_colour(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    preset = BUILTIN_PRESETS[1]

    resp = await authenticated_client.post(f"/api/branding/presets/{preset.key}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["primary_color"] == preset.values["primary_color"]
    assert app.state.branding.settings.primary_color == preset.values["primary_color"]


async def test_applying_a_preset_preserves_identity_and_banner(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    # The whole point of restricting PRESET_FIELDS — a look must not wipe the
    # name an admin set or an outage notice that is currently live.
    await authenticated_client.put(
        "/api/branding/",
        json={"app_name": "Acme Corp", "banner_message": "Maintenance tonight"},
    )

    resp = await authenticated_client.post(f"/api/branding/presets/{BUILTIN_PRESETS[2].key}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["app_name"] == "Acme Corp"
    assert body["banner_message"] == "Maintenance tonight"


async def test_applying_a_preset_keeps_an_uploaded_logo(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    app.state.branding.settings.logo_file_id = "11111111-1111-1111-1111-111111111111"

    await authenticated_client.post(f"/api/branding/presets/{BUILTIN_PRESETS[0].key}")

    assert app.state.branding.settings.logo_file_id == "11111111-1111-1111-1111-111111111111"


async def test_an_unknown_preset_is_a_404(authenticated_client: httpx.AsyncClient) -> None:
    resp = await authenticated_client.post("/api/branding/presets/does-not-exist")
    assert resp.status_code == 404


async def test_applying_a_preset_requires_the_manage_permission(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.post(f"/api/branding/presets/{BUILTIN_PRESETS[0].key}")
    assert resp.status_code in (401, 403)


async def test_the_manage_page_lists_the_presets(
    authenticated_client: httpx.AsyncClient,
) -> None:
    page = await authenticated_client.get("/admin/branding/", follow_redirects=False)

    assert page.status_code == 200, page.status_code
    assert "presets" in page.text
    assert BUILTIN_PRESETS[0].label in page.text
