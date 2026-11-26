"""Pin the documented middleware execution order.

AGENTS.md spells out the pipeline:

    (ForwardedHost → ProxyHeaders, opt-in; pinned in test_forwarded_host.py)
    (SentryContext, only when Sentry is enabled)
    CorrelationId → RequestLogging → CORS → BodyLimit → GZip → Security
                  → <before_session> → Session → InertiaMiddleware → <default module>
                  → Tenant (opt-in) → Locale → <after_tenant> → InertiaLayoutData
                  → RateLimit → Setup → Maintenance
                  → CommitBeforeResponse → app

Setup runs before Maintenance: an install that has never been set up has
nothing meaningful to put into maintenance mode, so the setup redirect wins.
The outer adapter InertiaMiddleware protects both redirects and page payloads
from caching and varies HTML documents on X-Inertia.

Tenant/Locale must see ``request.state.user`` set by AuthMiddleware so
DB queries get filtered correctly; CorrelationId must wrap everything so
every log line carries its id. SiteLock must precede AuthMiddleware: it gates
anonymous visitors itself, and if Auth ran first they would be redirected to
the login page — revealing that a login form exists on a site that is meant
to be fully hidden. That inversion breaks the feature without failing any
site_lock unit test, which is why the order is pinned here.

DemoReadOnlyMiddleware is outermost of the module middlewares — ``users``
sorts last, so it wraps SiteLock and Auth. That is where it wants to be: it
refuses a demo session's writes before any handler, middleware side-effect or
DB session runs, and it reads the demo marker straight off the session rather
than ``request.state.user``, so it needs nothing Auth provides. It also
cannot hide SiteLock from an anonymous visitor, because acquiring a demo
session means POSTing to the demo endpoint, which SiteLock blocks first.

CookielessPublicFilesMiddleware (``file_storage``) keeps the session cookie and
``Vary: Cookie`` off anonymous public-file reads. Its place among the module
middlewares does not matter: it clears the session's accessed/modified flags as
the response starts, so reads by Auth or SiteLock further out are forgotten too.

Maintenance sits after InertiaLayoutData because its 503 page renders
through Inertia and needs the shared props (auth, menus, i18n) — placed any
further out it would render bare, with no layout and untranslated copy. It is
also after Auth, which is what tells it whether the caller is an admin allowed
to pass through and switch it back off.

CommitBeforeResponse is innermost so its send-wrapper is the first to see
``http.response.start`` — that is what makes the request's DB work commit
before any byte reaches the client (GH #257). Anything added inside it would
run after the commit.

GZip sits inside the observability pair so
those still see every request, but outside everything that produces a body
— including the /static mount, which is where compression pays off most.
BodyLimit sits just inside RequestLogging (a 413 is still logged) and outside
GZip and every module, so an oversized body is refused before anything reads
it. RateLimit sits after auth and locale/layout data: it
must know whether the caller is signed in, and its 429 page renders through
Inertia with the shared props.

Order matters and a swap is the kind of
regression that breaks production without breaking any happy-path test.
``app.user_middleware`` lists middlewares in execution order (Starlette
LIFOs ``add_middleware`` calls, FastAPI surfaces them already reversed).
"""

from __future__ import annotations

import pytest
from simple_module_hosting.boot.app_builder import create_app
from simple_module_hosting.config.settings import Settings

_EXPECTED_MULTI_TENANT = (
    "CorrelationIdMiddleware",
    "RequestLoggingMiddleware",
    "CorsMiddleware",
    "BodyLimitMiddleware",
    "HostGZipMiddleware",
    "SecurityHeadersMiddleware",
    "SessionMiddleware",
    "InertiaMiddleware",
    "DemoReadOnlyMiddleware",
    "SiteLockMiddleware",
    "CookielessPublicFilesMiddleware",
    "AuthMiddleware",
    "TenantMiddleware",
    "LocaleMiddleware",
    "InertiaLayoutDataMiddleware",
    "RateLimitMiddleware",
    "SetupMiddleware",
    "MaintenanceMiddleware",
    "CommitBeforeResponseMiddleware",
)

_EXPECTED_SINGLE_TENANT = (
    "CorrelationIdMiddleware",
    "RequestLoggingMiddleware",
    "CorsMiddleware",
    "BodyLimitMiddleware",
    "HostGZipMiddleware",
    "SecurityHeadersMiddleware",
    "SessionMiddleware",
    "InertiaMiddleware",
    "DemoReadOnlyMiddleware",
    "SiteLockMiddleware",
    "CookielessPublicFilesMiddleware",
    "AuthMiddleware",
    "LocaleMiddleware",
    "InertiaLayoutDataMiddleware",
    "RateLimitMiddleware",
    "SetupMiddleware",
    "MaintenanceMiddleware",
    "CommitBeforeResponseMiddleware",
)


def _names(app) -> tuple[str, ...]:
    return tuple(m.cls.__name__ for m in app.user_middleware)


@pytest.mark.parametrize(
    ("multi_tenant", "expected"),
    [(True, _EXPECTED_MULTI_TENANT), (False, _EXPECTED_SINGLE_TENANT)],
)
def test_middleware_pipeline_order(multi_tenant: bool, expected: tuple[str, ...]) -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="x" * 32,
        multi_tenant=multi_tenant,
    )
    app = create_app(settings)
    assert _names(app) == expected, (
        "Middleware pipeline order drifted from AGENTS.md. "
        f"Got {_names(app)!r}, expected {expected!r}."
    )


def test_tenant_middleware_absent_when_disabled() -> None:
    """``multi_tenant=False`` must not register TenantMiddleware at all.

    Just toggling off the header would still leak the DB context-var setter
    onto every request; the middleware itself is what must vanish.
    """
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="x" * 32,
        multi_tenant=False,
    )
    app = create_app(settings)
    assert "TenantMiddleware" not in _names(app)


@pytest.mark.parametrize("multi_tenant", [True, False])
def test_named_stages_preserve_dependency_order(settings, monkeypatch, multi_tenant):
    from simple_module_core import ModuleBase, ModuleMeta
    from simple_module_hosting import add_middleware
    from simple_module_hosting.boot import app_builder

    class Probe:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)

    class BeforeSession(Probe):
        pass

    class Default(Probe):
        pass

    class AfterTenant(Probe):
        pass

    class DependentAfterTenant(Probe):
        pass

    class First(ModuleBase):
        meta = ModuleMeta(name="First", depends_on=["Users"])

        def register_middleware(self, app):
            add_middleware(app, BeforeSession, stage="before_session")
            add_middleware(app, Default)
            add_middleware(app, AfterTenant, after="tenant")

    class Second(ModuleBase):
        meta = ModuleMeta(name="Second", depends_on=["First"])

        def register_middleware(self, app):
            add_middleware(app, DependentAfterTenant, stage="after_tenant")

    discover = app_builder.discover_modules
    monkeypatch.setattr(
        app_builder, "discover_modules", lambda **kw: [*discover(**kw), First(), Second()]
    )
    settings = settings.model_copy(update={"multi_tenant": multi_tenant})
    app = create_app(settings)
    expected = list(_EXPECTED_MULTI_TENANT if multi_tenant else _EXPECTED_SINGLE_TENANT)
    expected.insert(expected.index("SessionMiddleware"), "BeforeSession")
    expected.insert(expected.index("DemoReadOnlyMiddleware"), "Default")
    index = expected.index("InertiaLayoutDataMiddleware")
    expected[index:index] = ["DependentAfterTenant", "AfterTenant"]
    assert _names(app) == tuple(expected)
