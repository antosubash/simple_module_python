"""Pin the documented middleware execution order.

CLAUDE.md spells out the pipeline:

    CorrelationId → RequestLogging → GZip → Security → Session → <module>
                  → Tenant (opt-in) → Locale → InertiaLayoutData
                  → InertiaCache → Maintenance → CommitBeforeResponse → app

InertiaCache sits directly inside InertiaLayoutData, the middleware that puts
this user's auth block, permissions and menus into every Inertia payload. Being
inside it means its send-wrapper sees the response before anything else can
read the headers, and pairing the two keeps "what makes the payload per-user"
and "what stops the payload being cached" from drifting apart.

Maintenance sits inside InertiaCache rather than outside it. Its 503 is an
Inertia payload carrying the same per-user auth block and menus, and it is
produced by short-circuiting — so if it sat outside, that payload would never
pass through the cache guard and would ship storable, which is the exact bug
InertiaCache exists to prevent.

Tenant/Locale must see ``request.state.user`` set by AuthMiddleware so
DB queries get filtered correctly; CorrelationId must wrap everything so
every log line carries its id. SiteLock must precede AuthMiddleware: it gates
anonymous visitors itself, and if Auth ran first they would be redirected to
the login page — revealing that a login form exists on a site that is meant
to be fully hidden. That inversion breaks the feature without failing any
site_lock unit test, which is why the order is pinned here.

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
Order matters and a swap is the kind of
regression that breaks production without breaking any happy-path test.
``app.user_middleware`` lists middlewares in execution order (Starlette
LIFOs ``add_middleware`` calls, FastAPI surfaces them already reversed).
"""

from __future__ import annotations

import pytest
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings

_EXPECTED_MULTI_TENANT = (
    "CorrelationIdMiddleware",
    "RequestLoggingMiddleware",
    "GZipMiddleware",
    "SecurityHeadersMiddleware",
    "SessionMiddleware",
    "SiteLockMiddleware",
    "AuthMiddleware",
    "TenantMiddleware",
    "LocaleMiddleware",
    "InertiaLayoutDataMiddleware",
    "InertiaCacheMiddleware",
    "MaintenanceMiddleware",
    "CommitBeforeResponseMiddleware",
)

_EXPECTED_SINGLE_TENANT = (
    "CorrelationIdMiddleware",
    "RequestLoggingMiddleware",
    "GZipMiddleware",
    "SecurityHeadersMiddleware",
    "SessionMiddleware",
    "SiteLockMiddleware",
    "AuthMiddleware",
    "LocaleMiddleware",
    "InertiaLayoutDataMiddleware",
    "InertiaCacheMiddleware",
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
        "Middleware pipeline order drifted from CLAUDE.md. "
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
