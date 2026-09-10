"""The initial page must reach both a v2 and a v3 client.

Inertia 3's ``getInitialPageFromDOM`` reads
``<script data-page="app" type="application/json">`` and nothing else; v2 read
the ``data-page`` attribute on ``<div id="app">``. The adapter emits both so
the package can ship before the client migrates and keep working after.
"""

from __future__ import annotations

from jinja2 import Environment
from simple_module_inertia.templating import InertiaContext, InertiaExtension

PAGE_JSON = '{"component": "Home", "props": {"errors": {}}, "url": "/", "version": "v1"}'


def _render_body(data: str) -> str:
    env = Environment(extensions=[InertiaExtension], autoescape=False)
    template = env.from_string("{% inertia_body %}")
    context = InertiaContext(
        environment="development",
        dev_url="http://localhost:5173",
        css=[],
        js="http://localhost:5173/main.tsx",
        is_ssr=False,
        data=data,
    )
    return template.render(inertia=context)


def test_body_carries_the_v3_json_script_element() -> None:
    html = _render_body(PAGE_JSON)
    assert f'<script data-page="app" type="application/json">{PAGE_JSON}</script>' in html


def test_body_keeps_the_v2_data_page_attribute() -> None:
    html = _render_body(PAGE_JSON)
    assert f"<div id=\"app\" data-page='{PAGE_JSON}'></div>" in html


def test_body_orders_script_before_mount_point_then_entry_module() -> None:
    html = _render_body(PAGE_JSON)
    script_at = html.index('<script data-page="app"')
    div_at = html.index('<div id="app"')
    entry_at = html.index('<script type="module" src="http://localhost:5173/main.tsx">')
    assert script_at < div_at < entry_at
