"""The request-scoped facade. Thin: each stage lives in its own module."""

from __future__ import annotations

from typing import Any, cast

from fastapi import Request
from jinja2.utils import htmlsafe_json_dumps
from pydantic import BaseModel
from starlette.responses import RedirectResponse, Response

from simple_module_inertia.config import InertiaConfig, resolved_version
from simple_module_inertia.errors import InertiaVersionConflictException
from simple_module_inertia.manifest import entry_assets
from simple_module_inertia.page import build_page, encode_page
from simple_module_inertia.request import InertiaRequest
from simple_module_inertia.resolve import resolve_props
from simple_module_inertia.response import (
    InertiaResponse,
    fragment_redirect,
    json_response,
    location,
    redirect,
)
from simple_module_inertia.templating import InertiaContext


class Inertia:
    def __init__(self, request: Request, config: InertiaConfig, client: Any = None) -> None:
        self._request = request
        self._config = config
        self._client = client  # kept for signature compatibility; SSR is not implemented
        self._req = InertiaRequest.from_headers(request.headers, request.method)
        self._version = resolved_version(config)
        self._shared: dict[str, Any] = {}
        self._encrypt_history = False
        self._clear_history = False
        self._preserve_fragment = False
        if self._is_stale():
            raise InertiaVersionConflictException(url=str(request.url))

    # -- request state ----------------------------------------------------

    def _is_stale(self) -> bool:
        """Only a GET is rejected; the client re-submits mutations itself."""
        return (
            self._req.is_inertia
            and self._req.method == "GET"
            and self._req.version is not None
            and self._req.version != self._version
        )

    def share(self, **props: Any) -> None:
        self._shared.update(props)

    def flash(self, message: str, category: str) -> None:
        if not self._config.use_flash_messages:
            raise NotImplementedError("Flash messages are not enabled")
        self._request.session.setdefault("_messages", []).append(
            {"message": message, "category": category}
        )

    def encrypt_history(self) -> Inertia:
        self._encrypt_history = True
        return self

    def clear_history(self) -> Inertia:
        self._clear_history = True
        return self

    def preserve_fragment(self) -> Inertia:
        self._preserve_fragment = True
        return self

    # -- redirects --------------------------------------------------------

    def redirect(self, url: str) -> RedirectResponse:
        return redirect(url, method=self._request.method)

    def back(self) -> RedirectResponse:
        return self.redirect(self._request.headers.get("Referer", "/"))

    @staticmethod
    def location(url: str) -> Response:
        return location(url)

    @staticmethod
    def redirect_with_fragment(url: str) -> Response:
        return fragment_redirect(url)

    # -- render -----------------------------------------------------------

    def _pop_session(self, key: str, default: Any) -> Any:
        session = self._request.session
        return session.pop(key) if key in session else default

    async def render(
        self, component: str, props: dict[str, Any] | BaseModel | None = None
    ) -> InertiaResponse:
        page_props: dict[str, Any] = (
            props.model_dump() if isinstance(props, BaseModel) else dict(props or {})
        )
        if self._config.use_flash_messages:
            page_props[self._config.flash_message_key] = self._pop_session("_messages", [])
        errors = self._pop_session("_errors", {}) if self._config.use_flash_errors else {}
        # ``errors`` is the protocol's always-prop; keep the configured key
        # pointing at the same dict so a custom flash_error_key still works.
        if self._config.flash_error_key != "errors":
            page_props[self._config.flash_error_key] = errors

        resolved = await resolve_props(page_props, self._shared, component, self._req)
        page = build_page(
            component=component,
            resolved=resolved,
            url=str(self._request.url),
            version=self._version,
            errors=errors,
            encrypt_history=self._encrypt_history,
            clear_history=self._clear_history,
            preserve_fragment=self._preserve_fragment,
        )
        if self._req.is_inertia:
            return json_response(page)
        return self._render_html(page)

    def _render_html(self, page: dict[str, Any]) -> InertiaResponse:
        files = entry_assets(self._config)
        # encode_page yields a JSON-safe dict; htmlsafe_json_dumps serialises it
        # exactly once with HTML-safe escaping. Passing a pre-dumped string here
        # would double-encode the page object into a quoted JSON literal.
        page_json = htmlsafe_json_dumps(encode_page(page))
        context = {
            "inertia": InertiaContext(
                environment=self._config.environment,
                dev_url=self._config.dev_url,
                is_ssr=False,
                data=cast(str, page_json),
                js=files.js,
                css=files.css,
            ),
            **self._config.extra_template_context,
        }
        return self._config.templates.TemplateResponse(
            name=self._config.root_template_filename, request=self._request, context=context
        )
