"""#535 step 1 through the real host: template, branding title, ``public_base_url``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_inertia import Head

_PATH = "/__seo_probe"
_BASE = "https://example.org"


@pytest.fixture
def probe(app):
    @app.get(_PATH)
    async def _probe(inertia: InertiaDep):
        head = Head(
            title="Probe",
            description="desc",
            canonical="/probe",
            og={"image": "/i.png"},
            json_ld=[{"@type": "WebPage", "name": "</script><script>x</script>"}],
        )
        return await inertia.render("Probe/Page", {}, head=head)

    app.state.host.settings.public_base_url = _BASE
    return app


async def test_first_response_has_head_tags_without_js(probe, authenticated_client) -> None:
    html = (await authenticated_client.get(_PATH)).text
    assert html.count("<title") == 1
    assert '<title data-inertia="">Probe — ' in html
    assert 'rel="canonical" href="https://example.org/probe"' in html
    assert 'property="og:url" content="https://example.org/probe"' in html
    assert 'property="og:image" content="https://example.org/i.png"' in html
    assert "</script><script>x" not in html


async def test_forged_host_never_reaches_canonical(probe, authenticated_client) -> None:
    html = (await authenticated_client.get(_PATH, headers={"Host": "attacker.test"})).text
    assert "attacker.test" not in html
    assert 'href="https://example.org/probe"' in html


async def test_public_base_url_is_read_per_request(probe, authenticated_client) -> None:
    probe.state.host.settings.public_base_url = "https://other.example"
    html = (await authenticated_client.get(_PATH)).text
    assert 'href="https://other.example/probe"' in html


async def test_client_visit_gets_head_prop(probe, authenticated_client) -> None:
    body = (await authenticated_client.get(_PATH, headers={"X-Inertia": "true"})).json()
    assert any('rel="canonical"' in tag for tag in body["props"]["_head"])


def test_public_base_url_validation() -> None:
    assert HostSettings(public_base_url=" https://example.org/ ").public_base_url == _BASE
    assert HostSettings(public_base_url="").public_base_url == ""
    with pytest.raises(ValidationError):
        HostSettings(public_base_url="javascript:alert(1)")
