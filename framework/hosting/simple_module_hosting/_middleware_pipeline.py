"""Middleware pipeline installation, CSP choice and session-cookie security."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from simple_module_core.app_state import get_body_limits
from simple_module_db import CommitBeforeResponseMiddleware
from simple_module_inertia import InertiaMiddleware
from starlette.middleware.gzip import GZipMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from simple_module_hosting import sentry
from simple_module_hosting._body_limit import BodyLimitMiddleware
from simple_module_hosting._cors import CorsMiddleware
from simple_module_hosting._forwarded_host import ForwardedHostMiddleware
from simple_module_hosting._rate_limit import RateLimitMiddleware
from simple_module_hosting._server_timing import ServerTimingMiddleware
from simple_module_hosting.auth_policy import session_cookie_is_secure
from simple_module_hosting.i18n_middleware import LocaleMiddleware
from simple_module_hosting.maintenance import MaintenanceMiddleware
from simple_module_hosting.middleware import (
    CorrelationIdMiddleware,
    InertiaLayoutDataMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    TenantMiddleware,
)
from simple_module_hosting.middleware_config import finalize_middleware
from simple_module_hosting.session import SessionMiddleware
from simple_module_hosting.settings import Settings
from simple_module_hosting.setup_gate import SetupMiddleware

if TYPE_CHECKING:
    from simple_module_core.csp import CspSourceRegistry
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry
    from simple_module_core.rate_limit import WindowStore


# Below this, gzip framing costs more than it saves. Starlette's own default.
COMPRESSION_MIN_BYTES = 500

# Starlette defaults to 9, which buys almost nothing on JSON and HTML: a 76 KB
# first-load page compresses 1.2% smaller at 9 than at 5, for 2.4x the CPU
# (6.4 ms vs 2.7 ms), spent on the event loop that serves every other request.
COMPRESSION_LEVEL = 5


def build_csp(settings: Settings, csp_registry: CspSourceRegistry) -> str:
    """Choose the CSP for this boot and fold in module-declared sources.

    Development gets the Vite-widened policy; production the strict default.
    ``csp_registry`` carries origins modules declared via
    ``register_csp_sources`` (e.g. an external font host) — merged here so
    both variants honor them. An empty registry leaves the policy unchanged.
    """
    base = (
        SecurityHeadersMiddleware.dev_csp(settings.vite_dev_url)
        if settings.is_development
        else SecurityHeadersMiddleware.DEFAULT_CSP
    )
    return csp_registry.extend_policy(base)


def install_inner_middleware(
    app: FastAPI,
    settings: Settings,
    modules: list,
    menu_registry: MenuRegistry,
    perm_registry: PermissionRegistry,
    rate_limit_store: WindowStore,
) -> None:
    """Install the inner pipeline and run module middleware hooks.

    Order matters: last added = first executed. Execution order:
    (ForwardedHost, if trusted_proxy and forwarded_host_allowlist) →
    (ProxyHeaders, if trusted_proxy) → CorrelationId → RequestLogging →
    (ServerTiming, development only) → CORS → BodyLimit → GZip → Security →
    [before_session] → Session → InertiaMiddleware → [default module] →
    (Tenant, if multi_tenant or default_tenant) → Locale → [after_tenant] → InertiaLayoutData →
    RateLimit → Setup → Maintenance → CommitBeforeResponse.
    """
    # Added first, so it is innermost and its send-wrapper is the first to see
    # the response: the request's DB work commits before any byte reaches the
    # client, instead of in get_db's post-response exit code (GH #257).
    app.add_middleware(CommitBeforeResponseMiddleware)
    # Auth, locale and lazy layout resolution must precede the maintenance page.
    # The outer adapter middleware applies protocol and cache rules to it: the
    # 503 renders through Inertia with this user's auth block and menus, so it
    # must stay non-cacheable like any other payload (GH #272).
    app.add_middleware(MaintenanceMiddleware)
    # An install awaiting setup takes precedence over maintenance mode.
    app.add_middleware(SetupMiddleware)
    # Auth and locale are available when rendering a rate-limit error page.
    app.add_middleware(
        RateLimitMiddleware,
        public_rate=None,
        store=rate_limit_store,
    )
    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=menu_registry,
        permission_registry=perm_registry,
    )
    app.add_middleware(
        LocaleMiddleware,
        supported_locales=settings.i18n_supported_locales,
        default_locale=settings.i18n_default_locale,
        cookie_name=settings.i18n_cookie_name,
    )
    if settings.multi_tenant:
        app.add_middleware(TenantMiddleware, header=settings.tenant_header or None)
    elif settings.default_tenant:
        # Single-tenant host with tenant-scoped tables: every request is the
        # one tenant (#359). Never used with multi_tenant — no shared fallback.
        app.add_middleware(TenantMiddleware, fixed=settings.default_tenant)
    for mod in modules:
        mod.register_middleware(app)


def install_middleware(app: FastAPI, settings: Settings, csp_registry: CspSourceRegistry) -> None:
    """Finish outer layers, then apply named stages and host overrides."""
    # Outside the default/after_tenant stages and cache guard, so it normalises
    # the final response — including redirects a module middleware issues
    # itself (an expired session's login redirect after a DELETE must still
    # become a 303) — while Session, further out, still sees its result.
    app.add_middleware(InertiaMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        secret_key_provider=lambda: app.state.sm.settings.secret_key,
        https_only=session_cookie_is_secure(settings),
    )
    # In dev, relax CSP so the browser can fetch @vite/client, main.tsx, and
    # the HMR WebSocket from the Vite origin (build_csp picks the variant).
    # HSTS is suppressed in dev because it runs over plain HTTP on loopback.
    security_kwargs: dict[str, str | None] = {
        "content_security_policy": build_csp(settings, csp_registry)
    }
    if settings.is_development:
        security_kwargs["strict_transport_security"] = None
    # Providers registered via ``registry.add_provider`` follow DB-backed
    # settings, so the middleware evaluates them per response (#434).
    app.add_middleware(SecurityHeadersMiddleware, csp_registry=csp_registry, **security_kwargs)
    # Compress response bodies. Added here so it sits inside CorrelationId and
    # RequestLogging (which set headers and read request state) but outside
    # everything that produces a body — including the /static mount, where it
    # matters most: the built CSS is ~139 KB raw and ~21 KB gzipped, and the
    # JS bundle compresses about 3x. Uncompressed assets dominated cold page
    # load, several times larger than anything on the server request path.
    app.add_middleware(
        GZipMiddleware, minimum_size=COMPRESSION_MIN_BYTES, compresslevel=COMPRESSION_LEVEL
    )
    # Right inside RequestLogging (so a 413 is logged) and outside GZip and the
    # whole module tier: an oversized body is refused before anything reads it.
    app.add_middleware(
        BodyLimitMiddleware,
        max_bytes=0,
        registry=get_body_limits(app),
    )
    # CORS executes between RequestLogging and BodyLimit: preflights are answered
    # before auth, rate limit, setup and maintenance can reject them, and a 413
    # still carries the headers. The host's ``/api/`` policy joins the modules'.
    cors_registry = app.state.cors_policies
    app.add_middleware(CorsMiddleware, registry=cors_registry)
    if settings.is_development:
        # Inside RequestLogging, outside everything that does work: its ``app``
        # time covers the whole pipeline and every query the request ran.
        app.add_middleware(ServerTimingMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    if sentry.is_enabled():
        app.add_middleware(sentry.SentryContextMiddleware)
    # Outermost: rewrite scheme/client from X-Forwarded-* before anything else
    # reads them, so request logs see the real client IP rather than the
    # proxy's. Inertia no longer needs this: its page url is
    # root-relative, so pushState can't see a cross-scheme url either way (it
    # used to throw a SecurityError on every page — GH #223). Gated on an
    # explicit trust setting — never trust forwarded headers by default.
    if settings.trusted_proxy:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxy)
    # Added after ProxyHeaders so it executes before it, while the TCP peer is
    # still the proxy (#528). Needs both a trusted proxy and an allowlist.
    if settings.forwarded_host_allowlist and settings.trusted_proxy:
        app.add_middleware(
            ForwardedHostMiddleware,
            trusted_hosts=settings.trusted_proxy,
            allowlist=settings.forwarded_host_allowlist,
        )
    finalize_middleware(app)
