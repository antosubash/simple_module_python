"""Nonce-bearing scripts and intersecting response policies (#785)."""

from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from jinja2 import Environment, FileSystemLoader
from simple_module_core.csp import CspSourceRegistry
from simple_module_hosting.middleware import SecurityHeadersMiddleware
from simple_module_inertia.templating import InertiaContext, InertiaExtension
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Route

_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES = [
    _ROOT / "host/templates",
    _ROOT / "framework/cli/simple_module_cli/templates/host/templates",
]
_CSP = "content-security-policy"


class Scripts(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.scripts = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts.append(dict(attrs))


@pytest.mark.parametrize("template_dir", _TEMPLATES, ids=["host", "scaffold"])
@pytest.mark.parametrize("environment", ["production", "development"])
async def test_scripts_share_the_request_nonce(template_dir, environment):
    env = Environment(
        loader=FileSystemLoader(template_dir), extensions=[InertiaExtension], autoescape=True
    )
    env.globals["branding_head"] = lambda request: SimpleNamespace(
        app_name="Test", theme_color="", favicon_url=""
    )
    config = SimpleNamespace(environment=environment, dev_url="http://localhost:5050")

    async def page(request):
        return HTMLResponse(
            env.get_template("index.html").render(
                request=request,
                inertia=InertiaContext(
                    environment=environment,
                    dev_url=config.dev_url,
                    css=[],
                    js="/static/app.js",
                    is_ssr=False,
                    data="{}",
                ),
            )
        )

    app = Starlette(routes=[Route("/", page)])
    app.state.sm = SimpleNamespace(inertia_config=config)
    registry = CspSourceRegistry()
    registry.add("script-src", "https://scripts.example")
    registry.add_provider(lambda app: [("script-src", "https://dynamic.example")])
    app.add_middleware(
        SecurityHeadersMiddleware,
        content_security_policy=registry.extend_policy(
            SecurityHeadersMiddleware.dev_csp(config.dev_url)
            if environment == "development"
            else SecurityHeadersMiddleware.DEFAULT_CSP
        ),
        csp_registry=registry,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first, second = await client.get("/"), await client.get("/")
    scripts = Scripts(first.text).scripts
    executable = [s for s in scripts if s.get("type") != "application/json"]
    nonce = executable[0].get("nonce")
    assert nonce
    assert all(s.get("nonce") == nonce for s in executable)
    assert Scripts(second.text).scripts[-1]["nonce"] != nonce
    csp = first.headers[_CSP]
    assert "https://scripts.example" in csp
    assert "https://dynamic.example" in csp
    if environment == "production":
        for directive in ("script-src", "script-src-elem"):
            assert f"{directive} 'self' 'nonce-{nonce}' 'strict-dynamic'" in csp
        assert "'unsafe-eval'" not in csp
        assert "'unsafe-inline'" not in csp.split("style-src")[0]
    else:
        assert "'unsafe-eval'" in csp and "'unsafe-inline'" in csp
        assert config.dev_url in csp
        assert any(s.get("src", "").endswith("/@vite/client") for s in scripts)


@pytest.mark.parametrize("own", ["sandbox allow-scripts; script-src *", "SANDBOX\tallow-scripts"])
async def test_sandbox_response_keeps_both_policies(own):
    async def page(request):
        return PlainTextResponse("ok", headers={_CSP: own})

    app = SecurityHeadersMiddleware(Starlette(routes=[Route("/", page)]))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")
    policies = response.headers.get_list(_CSP)
    assert len(policies) == 2
    assert own in policies
    app_policy = next(policy for policy in policies if policy != own)
    for directive in (
        "frame-ancestors 'self'",
        "base-uri 'self'",
        "form-action 'self'",
        "default-src 'self'",
    ):
        assert directive in app_policy
