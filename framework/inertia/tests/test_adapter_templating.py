"""The initial page reaches the v3 client once, through its JSON script."""

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


def test_body_has_a_bare_mount_point_and_only_one_page_copy() -> None:
    html = _render_body(PAGE_JSON)
    assert '<div id="app"></div>' in html
    assert html.count(PAGE_JSON) == 1


def test_body_orders_script_before_mount_point_then_entry_module() -> None:
    html = _render_body(PAGE_JSON)
    script_at = html.index('<script data-page="app"')
    div_at = html.index('<div id="app"')
    entry_at = html.index('<script type="module" src="http://localhost:5173/main.tsx">')
    assert script_at < div_at < entry_at
