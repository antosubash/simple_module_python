"""Pin the documented middleware execution order.

CLAUDE.md spells out the pipeline:

    CorrelationId → RequestLogging → GZip → Security → Session → <module>
                  → Tenant (opt-in) → Locale → InertiaLayoutData → app

Tenant/Locale must see ``request.state.user`` set by AuthMiddleware so
DB queries get filtered correctly; CorrelationId must wrap everything so
every log line carries its id. SiteLock must precede AuthMiddleware: it gates
anonymous visitors itself, and if Auth ran first they would be redirected to
the login page — revealing that a login form exists on a site that is meant
to be fully hidden. That inversion breaks the feature without failing any
site_lock unit test, which is why the order is pinned here.

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
