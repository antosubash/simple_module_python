"""Server-rendered ``<head>``: escaping, URL policy, markers, the ``_head`` prop."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.templating import Jinja2Templates
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from simple_module_inertia import (
    Head,
    Inertia,
    InertiaConfig,
    SiteInfo,
    inertia_dependency_factory,
)
from simple_module_inertia.head import head_tags
from starlette.middleware.sessions import SessionMiddleware

TEMPLATE = (
    "<!doctype html><html><head>"
    '{% if not inertia.has_head_title %}<title data-inertia="">Default</title>{% endif %}'
    "{% inertia_head %}</head><body>{% inertia_body %}</body></html>"
)
BASE = "https://example.org"
EVIL = "</script><script>alert(1)</script><!--"


def _app(tmp_path: Path, head: Head | None, base_url: str = BASE) -> FastAPI:
    (tmp_path / "index.html").write_text(TEMPLATE)
    config = InertiaConfig(
        templates=Jinja2Templates(directory=str(tmp_path)),
        entrypoint_filename="main.tsx",
        root_directory=".",
        site=lambda _request: SiteInfo(base_url=base_url, app_name="Acme"),
    )
    dep = inertia_dependency_factory(config)
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")

    @app.get("/p")
    async def page(inertia: Inertia = Depends(dep)):
        return await inertia.render("Public/Page", {}, head=head)

    return app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://evil.example")


async def test_document_carries_title_meta_og_and_canonical(tmp_path) -> None:
    head = Head(
        title="Maps",
        description='A "quoted" <b>desc</b>',
        canonical="/maps",
        robots="noindex, follow",
        og={"image": "/img/a.png", "type": "website"},
        twitter={"card": "summary"},
    )
    async with _client(_app(tmp_path, head)) as client:
        html = (await client.get("/p")).text
    assert html.count("<title") == 1
    assert '<title data-inertia="">Maps — Acme</title>' in html
    assert 'name="description"' in html and "&#34;quoted&#34; &lt;b&gt;" in html
    assert 'rel="canonical" href="https://example.org/maps"' in html
    assert 'property="og:url" content="https://example.org/maps"' in html
    assert 'property="og:title" content="Maps"' in html
    assert 'property="og:image" content="https://example.org/img/a.png"' in html
    assert 'name="twitter:card" content="summary"' in html
    assert 'name="robots" content="noindex, follow"' in html
    assert "Default" not in html


async def test_no_head_keeps_the_template_default_title(tmp_path) -> None:
    async with _client(_app(tmp_path, None)) as client:
        html = (await client.get("/p")).text
    assert '<title data-inertia="">Default</title>' in html
    assert "og:" not in html


async def test_forged_host_does_not_change_canonical(tmp_path) -> None:
    app = _app(tmp_path, Head(title="T", canonical="/maps"))
    async with _client(app) as client:
        html = (await client.get("/p", headers={"Host": "attacker.test"})).text
    assert "attacker" not in html
    assert 'href="https://example.org/maps"' in html


async def test_relative_urls_are_dropped_without_a_base_url(tmp_path) -> None:
    app = _app(tmp_path, Head(title="T", canonical="/maps", og={"image": "/a.png"}), base_url="")
    async with _client(app) as client:
        html = (await client.get("/p")).text
    assert "canonical" not in html
    assert "og:image" not in html and "og:url" not in html


async def test_json_ld_cannot_break_out_of_the_script_element(tmp_path) -> None:
    head = Head(title="T", json_ld=[{"@type": "Article", "name": EVIL}])
    async with _client(_app(tmp_path, head)) as client:
        html = (await client.get("/p")).text
    block = re.search(r'<script data-inertia="sm-jsonld-0"[^>]*>(.*?)</script>', html, re.S)
    assert block is not None
    assert "<" not in block.group(1) and ">" not in block.group(1)
    assert json.loads(block.group(1))["name"] == EVIL
    assert "<script>alert(1)" not in html


async def test_titles_and_text_are_escaped(tmp_path) -> None:
    async with _client(_app(tmp_path, Head(title=EVIL))) as client:
        html = (await client.get("/p")).text
    assert "<script>alert(1)" not in html


async def test_inertia_visit_carries_head_prop_with_replaceable_keys(tmp_path) -> None:
    head = Head(title="Maps", description="d", canonical="/maps")
    async with _client(_app(tmp_path, head)) as client:
        body = (await client.get("/p", headers={"X-Inertia": "true"})).json()
    tags = body["props"]["_head"]
    assert any(t.startswith("<title") for t in tags)
    assert all('data-inertia="' in t for t in tags)


@pytest.mark.parametrize(
    "bad",
    [
        {"canonical": "javascript:alert(1)"},
        {"canonical": "//evil.example/x"},
        {"canonical": "data:text/html,x"},
        {"og": {"image": "javascript:alert(1)"}},
        {"og": {"url": "ftp://x/y"}},
        {"twitter": {"image": "data:image/png;base64,AAAA"}},
        {"og": {'x" onload="y': "v"}},
        {"robots": "<script>"},
    ],
)
def test_non_http_urls_and_bad_keys_are_rejected(bad) -> None:
    with pytest.raises(ValidationError):
        Head(**bad)


def test_head_tags_use_only_data_inertia_keyed_elements() -> None:
    tags = head_tags(Head(title="T", description="d"), SiteInfo(app_name=""))
    assert tags[0] == '<title data-inertia="">T</title>'
    assert all("data-inertia" in t for t in tags)
