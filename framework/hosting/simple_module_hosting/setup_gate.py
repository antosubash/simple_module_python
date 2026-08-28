"""Serve the first-run wizard while the install is not yet usable.

A fresh deployment has no administrator, so without this every route either
redirects to a login nobody can pass or fails outright. While any required
:class:`~simple_module_core.setup_steps.SetupStep` reports incomplete, this
redirects to ``/setup``.

Sits inside ``InertiaCache`` in the middleware pipeline so its redirect is
never stored by a cache, and outside ``Maintenance`` — an install that is not
set up has nothing to put into maintenance.
"""

from __future__ import annotations

import logging
import time

from starlette.datastructures import Headers
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

SETUP_PATH = "/setup"

# How long a completeness verdict may be reused before the steps are re-run.
#
# Recomputing per request is what makes an install that loses its last
# administrator recoverable through the browser, but every evaluation costs a
# session checkout and a `SELECT COUNT(*)` on users — paid on every request
# for the entire life of an install that finished setup months ago. A few
# seconds of staleness buys that back while keeping the recovery property:
# the wizard reappears within the window rather than only after a restart.
_VERDICT_TTL_SECONDS = 5.0

# Paths that must answer during setup. /setup itself for obvious reasons;
# /static because the wizard is a real Inertia page that needs its assets, and
# redirecting them to HTML breaks the page that reports the problem; /health
# because an orchestrator killing the container mid-setup is not helpful.
_EXEMPT_PREFIXES = (SETUP_PATH, "/static", "/health")


STEP_MIGRATIONS = "host.migrations"


async def _database_migrated(app) -> bool:
    """Whether the schema is at head.

    Reads ``app.state.migration``, which the lifespan populates before any
    module starts. Defaults to ``True`` when absent so a build without Alembic
    is never gated on a migration it does not have.

    When that snapshot says *behind*, it is re-read from the database rather
    than trusted. The snapshot is taken once at boot, and the ordinary way to
    fix a behind-head schema is ``make migrate`` in a shell or a sidecar —
    which this process never observes. Without the re-read, an install that
    has already been repaired stays redirected to the wizard until someone
    restarts it. Only the behind-head branch pays for the query, so a healthy
    install still answers from the snapshot.
    """
    status = getattr(app.state, "migration", None)
    if not status:
        return True
    if status.get("is_current", True):
        return True

    from simple_module_hosting.migrations import migration_status

    try:
        status = await migration_status(app.state.sm.db.engine)
    except Exception as exc:
        logger.debug("Migration re-check failed, using the boot snapshot: %s", exc)
        return False
    app.state.migration = status
    return bool(status["is_current"])


def register_migration_step(registry) -> None:
    """Contribute the host's own setup step: the schema must be at head.

    Host-owned rather than module-owned because no module owns the schema as a
    whole — it is the union of whatever modules are installed.
    """
    from simple_module_core.setup_steps import SetupStep

    registry.set_owner("Host")
    registry.add(
        SetupStep(
            id=STEP_MIGRATIONS,
            title="Apply database migrations",
            title_key="host.setup.steps.migrations.title",
            description="Bring the database schema up to the version this code expects.",
            description_key="host.setup.steps.migrations.description",
            is_complete=_database_migrated,
            order=20,
        )
    )
    registry.set_owner("")


class SetupMiddleware:
    """Redirect to the setup wizard until every required step is complete."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._verdict: bool | None = None
        self._verdict_expires: float = 0.0

    async def _is_complete(self, registry, starlette_app) -> bool:
        """``registry.is_setup_complete`` behind a short TTL cache.

        Only the *complete* verdict is cached, never the incomplete one. That
        asymmetry is the whole point:

        - "Complete" is the steady state of a configured install, held for
          months. Caching it is what saves the session checkout and
          ``SELECT COUNT(*)`` on every request, which is the cost worth
          removing.
        - "Incomplete" lasts minutes at most, and caching it strands the
          operator: the wizard creates the administrator and sends the browser
          back to ``/``, a stale negative redirects that to ``/setup``, and
          ``/setup`` has just started returning 404. The operator lands on a
          dead page at the moment setup succeeds.

        The cache lives on the middleware instance rather than on ``app.state``
        so it cannot leak between two apps built in the same process — the test
        suite builds many — and is discarded with the app that owns it.
        """
        now = time.monotonic()
        if self._verdict and now < self._verdict_expires:
            return True
        verdict = await registry.is_setup_complete(starlette_app)
        if verdict:
            self._verdict = True
            self._verdict_expires = now + _VERDICT_TTL_SECONDS
        return verdict

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path.startswith(_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        starlette_app = scope.get("app")
        registry = getattr(getattr(starlette_app, "state", None), "sm", None)
        registry = getattr(registry, "setup_registry", None)
        # No registry, or nothing registered a step: nothing can gate the app.
        # ``create_app`` always seeds ``host.migrations``, so in a real host
        # this only catches an app assembled by hand; the Keycloak case — no
        # local accounts, so a permanently empty users table — is handled by
        # that module contributing no step, which leaves the remaining steps
        # satisfiable.
        if not registry:
            await self.app(scope, receive, send)
            return

        if await self._is_complete(registry, starlette_app):
            await self.app(scope, receive, send)
            return

        await self._redirect(scope, receive, send)

    async def _redirect(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Send the browser to the wizard.

        Inertia requests get a 409 with ``X-Inertia-Location`` rather than a
        302: Inertia's client follows a redirect with an XHR and would then
        choke on the wizard's HTML document. The 409 tells it to do a full
        page visit instead.
        """
        headers = Headers(scope=scope)
        if headers.get("x-inertia"):
            response = RedirectResponse(SETUP_PATH, status_code=409)
            response.headers["X-Inertia-Location"] = SETUP_PATH
        else:
            response = RedirectResponse(SETUP_PATH, status_code=302)
        await response(scope, receive, send)
