"""Site-wide announcement banner (message + severity).

Ported from IIASA.GeoWiki's top banner (``MaxTopBannerMessageLength``,
``AllowedTopBannerSeverities``, ``NormalizeTopBannerSeverity``). The split
between the two validators is this module's existing convention, same as
``design_pack``: settings normalise (they hydrate from the DB and must never
stop a boot), the update DTO rejects (the API should say what was wrong).
"""

from __future__ import annotations

import httpx
import pytest
from branding.constants import MAX_BANNER_MESSAGE_LEN, normalize_banner_severity
from branding.contracts.schemas import BrandingUpdate
from branding.settings import BrandingSettings
from branding.shared_props import branding_payload

# ── Unit: settings normalise ───────────────────────────────────────────


def test_defaults_to_no_banner() -> None:
    s = BrandingSettings()
    assert s.banner_message == ""
    assert s.banner_severity == "info"


def test_message_is_trimmed_and_bounded() -> None:
    assert BrandingSettings(banner_message="  Down at 2am  ").banner_message == "Down at 2am"
    with pytest.raises(ValueError):
        BrandingSettings(banner_message="x" * (MAX_BANNER_MESSAGE_LEN + 1))


@pytest.mark.parametrize(
    ("stored", "expected"),
    [("info", "info"), ("WARNING", "warning"), (" danger ", "danger"), ("nonsense", "info")],
)
def test_settings_normalise_severity_rather_than_reject(stored: str, expected: str) -> None:
    # A severity that a future release renames must degrade to a readable
    # banner at boot, not refuse to start.
    assert BrandingSettings(banner_severity=stored).banner_severity == expected


def test_normalize_helper_handles_none_and_blank() -> None:
    assert normalize_banner_severity(None) == "info"
    assert normalize_banner_severity("  ") == "info"


# ── Unit: shared-props payload ─────────────────────────────────────────


def test_payload_omits_the_banner_when_there_is_no_message() -> None:
    # None, not an empty string — otherwise the frontend renders an empty bar.
    assert branding_payload(BrandingSettings())["banner"] is None


def test_payload_omits_the_banner_when_only_a_severity_is_set() -> None:
    assert branding_payload(BrandingSettings(banner_severity="danger"))["banner"] is None


def test_payload_carries_message_and_severity() -> None:
    payload = branding_payload(
        BrandingSettings(banner_message="Maintenance", banner_severity="warning")
    )
    assert payload["banner"] == {"message": "Maintenance", "severity": "warning"}


# ── Unit: update DTO is strict ─────────────────────────────────────────


def test_dto_accepts_a_known_severity_case_insensitively() -> None:
    assert BrandingUpdate(banner_severity="DANGER").banner_severity == "danger"


def test_dto_rejects_an_unknown_severity() -> None:
    # Unlike the settings validator: a typo should be a 422, not a silent "info".
    with pytest.raises(ValueError):
        BrandingUpdate(banner_severity="critical")


def test_dto_rejects_an_overlong_message() -> None:
    with pytest.raises(ValueError):
        BrandingUpdate(banner_message="x" * (MAX_BANNER_MESSAGE_LEN + 1))


# ── Integration ────────────────────────────────────────────────────────


async def test_setting_a_banner_persists_and_hot_swaps(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    resp = await authenticated_client.put(
        "/api/branding/",
        json={"banner_message": "Scheduled maintenance", "banner_severity": "warning"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["banner_message"] == "Scheduled maintenance"
    assert app.state.branding.settings.banner_severity == "warning"
    assert branding_payload(app.state.branding.settings)["banner"] is not None


async def test_clearing_the_message_hides_the_banner(
    app, authenticated_client: httpx.AsyncClient
) -> None:
    await authenticated_client.put("/api/branding/", json={"banner_message": "Temporary"})

    resp = await authenticated_client.put("/api/branding/", json={"banner_message": ""})

    assert resp.status_code == 200, resp.text
    assert branding_payload(app.state.branding.settings)["banner"] is None


async def test_api_rejects_an_unknown_severity(authenticated_client: httpx.AsyncClient) -> None:
    resp = await authenticated_client.put("/api/branding/", json={"banner_severity": "critical"})
    assert resp.status_code == 422


async def test_the_banner_reaches_a_logged_out_visitor(
    app, client: httpx.AsyncClient, authenticated_client: httpx.AsyncClient
) -> None:
    # An outage notice is most useful to people who cannot sign in, so it has
    # to be in the guest shell's shared props too.
    await authenticated_client.put(
        "/api/branding/", json={"banner_message": "Login is degraded", "banner_severity": "danger"}
    )

    page = await client.get("/users/login", follow_redirects=False)

    assert page.status_code == 200, page.status_code
    assert "Login is degraded" in page.text
