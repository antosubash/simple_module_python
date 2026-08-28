"""The first-run setup wizard.

Served while any required :class:`SetupStep` is incomplete — see
``simple_module_hosting.setup_gate``. Unauthenticated by necessity: it exists
precisely when no account exists yet.

Every route here refuses once setup completes. That is what bounds the
exposure of ``/setup/migrations``, which can run Alembic: it is reachable only
before an administrator exists, and closes permanently the moment one does.
``_require_setup_mode`` is applied to each route rather than assumed from the
middleware, because the middleware only *redirects* other paths to here — it
deliberately exempts ``/setup`` itself, so these handlers are the only thing
standing between a configured install and an open admin-creation form.

``/setup/administrator`` goes further and requires *its own* step to be
incomplete. "Some required step is incomplete" is not a safe gate for it: the
host always registers ``host.migrations``, so a live install whose schema
falls behind head — deploying code before the migration job runs — re-enters
setup mode with its administrators intact, and a route gated on the weaker
condition would let an anonymous request mint a fresh superuser there.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from inertia import InertiaResponse
from pydantic import EmailStr, Field
from simple_module_hosting.inertia_deps import InertiaDep
from sqlmodel import SQLModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup"])

_CHECK_DATABASE = "host.database"
_CHECK_REDIS = "background_tasks.redis"

_STEP_ADMINISTRATOR = "users.administrator"

# Mirrors ``UserManager.validate_password``. ``create_admin`` writes the hash
# directly and never goes through the manager, so without this the one
# unauthenticated account-creation route in the app is also the only one with
# no password policy at all.
_MIN_PASSWORD_LENGTH = 8


async def _pending_step_ids(request: Request) -> set[str]:
    """Ids of the required setup steps that are still incomplete."""
    registry = getattr(request.app.state.sm, "setup_registry", None)
    if not registry:
        return set()
    return {s.id for s in await registry.incomplete(request.app)}


async def _require_setup_mode(request: Request) -> None:
    """404 unless the install still has incomplete required setup steps."""
    if not await _pending_step_ids(request):
        raise HTTPException(status_code=404)


async def _require_pending_step(request: Request, step_id: str) -> None:
    """404 unless *step_id* specifically is still incomplete.

    The narrow gate, for routes whose effect only makes sense while that one
    step is outstanding — see the module docstring on why "setup mode" alone
    is too broad for admin creation.
    """
    if step_id not in await _pending_step_ids(request):
        raise HTTPException(status_code=404)


async def _run_check(request: Request, name: str) -> dict | None:
    """Run one registered health check by name and shape it for the UI.

    ``None`` when nothing registered that name — an install without the
    background_tasks module has no Redis to reach, and listing it as a failed
    connection would send an operator hunting for a service they don't run.
    """
    registry = request.app.state.sm.health_registry
    for check in registry.all_checks:
        if check.name != name:
            continue
        result = await check.check()
        return {
            "name": name,
            "status": str(result.status),
            # The reason is the point: "connection refused" and "authentication
            # failed" need different fixes.
            "detail": result.detail or "",
        }
    return None


async def _connection_status(request: Request) -> list[dict]:
    """Every dependency this install actually has, probed concurrently.

    Concurrently because each probe carries its own connect timeout: run in
    series, a wizard on a host where both the database and Redis are
    unreachable waits for the sum of them before rendering anything, which is
    exactly the case the wizard exists to diagnose.
    """
    results = await asyncio.gather(
        _run_check(request, _CHECK_DATABASE),
        _run_check(request, _CHECK_REDIS),
    )
    return [r for r in results if r is not None]


def _steps_payload(registry, pending_ids: set[str]) -> list[dict]:
    return [
        {
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "complete": s.id not in pending_ids,
        }
        for s in registry.all_steps
    ]


@router.get("", response_model=None)
@router.get("/", response_model=None)
async def setup_index(request: Request, inertia: InertiaDep) -> InertiaResponse:
    """The wizard itself: connection status, migrations, remaining steps."""
    await _require_setup_mode(request)

    registry = request.app.state.sm.setup_registry
    pending = {s.id for s in await registry.incomplete(request.app)}
    migration = getattr(request.app.state, "migration", None) or {}

    return await inertia.render(
        "Setup/Wizard",
        {
            "checks": await _connection_status(request),
            "steps": _steps_payload(registry, pending),
            "migration": {
                "current": migration.get("current_revision"),
                "head": migration.get("head_revision"),
                "isCurrent": bool(migration.get("is_current", True)),
            },
        },
    )


@router.post("/test-connections")
async def test_connections(request: Request) -> dict:
    """Re-run the connection checks without reloading the page."""
    await _require_setup_mode(request)
    return {"checks": await _connection_status(request)}


class AdministratorIn(SQLModel):
    email: EmailStr
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH)
    full_name: str | None = None


@router.post("/administrator")
async def create_administrator(request: Request, payload: AdministratorIn) -> dict:
    """Create the first administrator, which is what releases the gate."""
    await _require_pending_step(request, _STEP_ADMINISTRATOR)

    # Imported here, not at module scope: the host must not hard-depend on the
    # users module being installed. An install with an external identity
    # provider never reaches this route, because it registers no setup step.
    try:
        from users.bootstrap import create_admin
    except ImportError as exc:  # pragma: no cover - configuration error
        raise HTTPException(
            status_code=400,
            detail="No local accounts provider is installed.",
        ) from exc

    async with request.app.state.sm.db.session_factory() as session:
        result = await create_admin(
            session,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        )
        await session.commit()

    logger.info("Setup: administrator created (%s)", payload.email)
    return {"created": result.created, "email": payload.email}


@router.post("/migrations")
async def apply_migrations(request: Request) -> dict:
    """Run ``alembic upgrade head``.

    Reachable only while setup is incomplete (``_require_setup_mode``), which
    is what bounds an endpoint that can execute migrations over HTTP. An
    unmigrated database otherwise means dropping the operator to a shell — the
    sharpest edge in the whole onboarding path.
    """
    await _require_setup_mode(request)

    import asyncio

    from alembic import command
    from alembic.config import Config as AlembicConfig
    from simple_module_hosting.migrations import default_alembic_ini

    # Resolved through the hosting helper rather than hardcoded: this runs
    # inside a request, and a literal "host/alembic.ini" is only correct while
    # the process cwd happens to be the project root.
    ini_path = default_alembic_ini()

    def _upgrade() -> None:
        # "heads", not "head": each module's first migration sets its own
        # branch_labels, so the history legitimately has several heads and
        # "head" raises CommandError("Multiple head revisions are present").
        # This is what `make migrate` runs.
        command.upgrade(AlembicConfig(ini_path), "heads")

    try:
        await asyncio.to_thread(_upgrade)
    except Exception as exc:
        logger.exception("Setup: migration run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    from simple_module_hosting.migrations import migration_status

    request.app.state.migration = await migration_status(request.app.state.sm.db.engine)
    logger.info("Setup: migrations applied")
    return {"migration": request.app.state.migration}


class SiteBasicsIn(SQLModel):
    """The host settings the wizard may set.

    Only fields ``HostSettings`` actually declares belong here. ``site_name``
    used to be accepted, filtered back out just before the write, and then
    echoed in ``saved`` — so the wizard reported persisting a value that never
    reached the database. Branding owns the site name; it is not a host
    setting.
    """

    i18n_default_locale: str | None = None


@router.post("/site-basics")
async def save_site_basics(request: Request, payload: SiteBasicsIn) -> dict:
    """Persist the optional host settings collected by the wizard."""
    await _require_setup_mode(request)

    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not changes:
        return {"saved": {}}

    # importlib, not a static import: the host must not hard-depend on the
    # settings module, and SM009 forbids naming a plugin package from
    # framework code. The same reasoning applies here at the host layer.
    import importlib

    service_cls = importlib.import_module("settings.service").SettingService
    store_cls = importlib.import_module("settings.store").SettingsStore
    apply_changes = importlib.import_module("settings.reload").apply_changes_and_reload

    async with request.app.state.sm.db.session_factory() as session:
        store = store_cls(service_cls(session))
        await apply_changes_and_reload_safe(request, apply_changes, store, changes)
        await session.commit()

    return {"saved": changes}


async def apply_changes_and_reload_safe(request: Request, apply_changes, store, changes: dict):
    """Apply host settings changes, ignoring fields this build doesn't declare.

    A wizard shipped ahead of a module that declares a field should not 500 —
    it should save what it can.
    """
    try:
        return await apply_changes(
            request.app,
            request.app.state.sm.event_bus,
            store,
            package="host",
            changes=changes,
        )
    except KeyError as exc:
        logger.warning("Setup: skipping unknown host setting(s): %s", exc)
        return None
