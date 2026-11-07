"""Security response headers and per-request CSP nonces."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from simple_module_hosting._csp_dynamic import DynamicCsp

if TYPE_CHECKING:
    from simple_module_core.csp import CspSourceRegistry

_SCOPE_HTTP = "http"
_MSG_RESPONSE_START = "http.response.start"

# Security response header names
_HEADER_CSP = "Content-Security-Policy"
_HEADER_HSTS = "Strict-Transport-Security"

# Security response header values
_XCTO_NOSNIFF = "nosniff"
_XFO_SAMEORIGIN = "SAMEORIGIN"
# OWASP/MDN now recommend disabling the legacy XSS auditor — older
# browser implementations introduced reflected-XSS vectors of their own.
# Production CSP authorizes scripts with a per-request nonce.
_XXSS_DISABLED = "0"
_HTTP_NOT_MODIFIED = 304
_REFERRER_STRICT_ORIGIN = "strict-origin-when-cross-origin"


class SecurityHeadersMiddleware:
    """Add security headers to every response.

    ``content_security_policy`` and ``strict_transport_security`` accept a
    string to override the defaults, or ``None`` to suppress that header
    (useful in development when Vite's HMR client loads cross-origin scripts,
    or behind plain-HTTP loopbacks where HSTS would lock users out).
    """

    DEFAULT_CSP = (
        "default-src 'self'; "
        # The request nonce is inserted after static/dynamic sources are merged.
        # 'wasm-unsafe-eval' lets WebAssembly compile (see worker-src below)
        # without re-allowing JavaScript eval.
        "script-src 'self' 'strict-dynamic' 'wasm-unsafe-eval'; "
        "script-src-elem 'self' 'strict-dynamic'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: blob:; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "connect-src 'self'; "
        # Allow blob: workers — MapLibre, comlink, web-tree-sitter and most
        # WASM libs ship their worker as a Blob URL. `child-src` is the
        # legacy fallback some browsers consult before `worker-src`.
        "worker-src 'self' blob:; "
        "child-src 'self' blob:; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    _DEFAULT_HSTS = "max-age=31536000; includeSubDomains"

    @staticmethod
    def dev_csp(vite_dev_url: str) -> str:
        """Build a dev CSP that whitelists the Vite dev server.

        In development the browser fetches ``@vite/client``, ``main.tsx``, and
        React Refresh from the Vite origin (default ``http://localhost:5050``),
        and opens a WebSocket there for HMR. Those fail under the prod CSP,
        so we widen ``script-src*``/``connect-src``/``style-src`` for that
        origin only (including the ``ws://`` equivalent for HMR).
        """
        ws_url = vite_dev_url.replace("http://", "ws://").replace("https://", "wss://")
        return (
            "default-src 'self'; "
            f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {vite_dev_url}; "
            f"script-src-elem 'self' 'unsafe-inline' {vite_dev_url}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {vite_dev_url}; "
            "img-src 'self' data: blob:; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            f"connect-src 'self' {vite_dev_url} {ws_url}; "
            "worker-src 'self' blob:; "
            "child-src 'self' blob:; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

    def __init__(
        self,
        app: ASGIApp,
        *,
        content_security_policy: str | None = DEFAULT_CSP,
        strict_transport_security: str | None = _DEFAULT_HSTS,
        csp_registry: CspSourceRegistry | None = None,
    ) -> None:
        self.app = app
        self.csp = content_security_policy
        self.hsts = strict_transport_security
        self._static_headers = (
            (b"x-content-type-options", _XCTO_NOSNIFF.encode("latin-1")),
            (b"x-frame-options", _XFO_SAMEORIGIN.encode("latin-1")),
            (b"x-xss-protection", _XXSS_DISABLED.encode("latin-1")),
            (b"referrer-policy", _REFERRER_STRICT_ORIGIN.encode("latin-1")),
        )
        self._static_names = frozenset(name for name, _ in self._static_headers)
        # Providers (settings-driven origins, #434) are evaluated per response;
        # with none, the precomputed string above is the whole story.
        self._dynamic = (
            DynamicCsp(content_security_policy, csp_registry)
            if content_security_policy and csp_registry is not None and csp_registry.providers
            else None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        nonce = secrets.token_urlsafe(16)
        scope.setdefault("state", {})["csp_nonce"] = nonce

        async def send_with_headers(message: Message) -> None:
            if message["type"] == _MSG_RESPONSE_START:
                # Build a fresh list: the app's own list (or tuple) is never mutated.
                raw = [h for h in message.get("headers", ()) if h[0] not in self._static_names]
                raw.extend(self._static_headers)
                message["headers"] = raw
                headers = MutableHeaders(raw=raw)
                # A 304 refreshes the cached response's headers: a new nonce there
                # would no longer match the cached body, so keep the cached CSP.
                if self.csp and message.get("status") != _HTTP_NOT_MODIFIED:
                    # Separate policies intersect, so a response's own policy is
                    # kept beside the app policy: it can tighten a page (#870) but
                    # never relax default-src or frame-ancestors.
                    dyn = self._dynamic
                    policy = dyn.policy_for(scope.get("app")) if dyn else self.csp
                    policy = policy.replace("'strict-dynamic'", f"'nonce-{nonce}' 'strict-dynamic'")
                    if _HEADER_CSP in headers:
                        headers.append(_HEADER_CSP, policy)
                    else:
                        headers[_HEADER_CSP] = policy
                if self.hsts:
                    headers[_HEADER_HSTS] = self.hsts
            await send(message)

        await self.app(scope, receive, send_with_headers)
