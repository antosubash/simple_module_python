"""Jinja glue: the template context and the ``inertia_head``/``inertia_body`` tags.

Ported from upstream. The SSR branches stay so the template contract is the
same, but nothing in this package calls an SSR server.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jinja2 import nodes
from jinja2.ext import Extension
from jinja2.parser import Parser
from jinja2.runtime import Context
from markupsafe import Markup


@dataclass
class InertiaContext:
    environment: Literal["development", "production"]
    dev_url: str
    css: list[str]
    js: str
    is_ssr: bool
    data: str | None = None
    ssr_head: str | None = None
    ssr_body: str | None = None


class InertiaExtension(Extension):
    tags = {"inertia_head", "inertia_body"}  # noqa: RUF012 - Jinja declares this an instance attr

    def parse(self, parser: Parser) -> nodes.Node:
        tag_name = next(parser.stream).value
        lineno = parser.stream.current.lineno
        node = self.call_method(f"_render_{tag_name}", [nodes.ContextReference()], lineno=lineno)
        return nodes.Output([node]).set_lineno(lineno)

    def _render_inertia_head(self, context: Context) -> Markup:
        inertia: InertiaContext = context["inertia"]
        fragments: list[str] = []
        if inertia.environment == "development":
            fragments.append(
                f'<script type="module" src="{inertia.dev_url}/@vite/client"></script>'
            )
        if inertia.is_ssr:
            if inertia.ssr_head is None:
                raise ValueError("SSR is enabled but no SSR head was provided")
            fragments.append(inertia.ssr_head)
        fragments.extend(f'<link rel="stylesheet" href="{css}">' for css in inertia.css)
        return Markup("\n".join(fragments))

    def _render_inertia_body(self, context: Context) -> Markup:
        inertia: InertiaContext = context["inertia"]
        fragments: list[str] = []
        if inertia.is_ssr:
            if inertia.ssr_body is None:
                raise ValueError("SSR is enabled but no SSR body was provided")
            fragments.append(inertia.ssr_body)
        else:
            if inertia.data is None:
                raise ValueError("No data was provided for the Inertia page")
            # Inertia 3's getInitialPageFromDOM reads only the JSON script
            # element; Inertia 2 read only the data-page attribute. Emit both
            # so the adapter ships before the client migrates and keeps working
            # after. ``data`` is htmlsafe_json_dumps output, so it cannot break
            # out of either the attribute or the script element.
            fragments.append(
                f'<script data-page="app" type="application/json">{inertia.data}</script>'
            )
            fragments.append(f"<div id=\"app\" data-page='{inertia.data}'></div>")
        fragments.append(f'<script type="module" src="{inertia.js}"></script>')
        return Markup("\n".join(fragments))
