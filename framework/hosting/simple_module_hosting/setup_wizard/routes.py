"""The first-run setup wizard's HTTP surface.

Served while any required :class:`SetupStep` is incomplete — see
``simple_module_hosting.setup_gate``. Unauthenticated by necessity: it exists
precisely when no account exists yet.

Two gates, deliberately of different widths:

* The page and the connection probe answer while *any* required step is
  incomplete ("setup mode"), and 404 the moment none is. The middleware only
  *redirects* other paths here — it exempts ``/setup`` itself — so these
  handlers are the only thing that makes the wizard disappear on a configured
  install.
* ``POST /setup/steps/<id>`` additionally requires **that step** to be
  incomplete. "Setup mode" is not a safe gate for an action: the host always
  registers ``host.migrations``, so a live install whose schema falls behind
  head — code deployed before the migration job ran — re-enters setup mode
  with its administrators intact. Gated on the weaker condition, the
  administrator step's action would let an anonymous request mint a fresh
  superuser there. The step-level check answers 409.

Every mutation carries the session-bound CSRF token (``RequiresCsrf``): the
page hands it out as the ``csrfToken`` prop and echoes it as ``X-CSRF-Token``.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from simple_module_inertia import InertiaResponse

from simple_module_hosting.csrf import RequiresCsrf, get_csrf_token
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.setup_wizard.payloads import connection_status, steps_payload

logger = logging.getLogger(__name__)

#: The Inertia page — ``Setup`` is the name the wizard's pages directory is
#: registered under in ``modules.generated.ts``; see ``setup_wizard.PAGES_NAME``.
_PAGE_WIZARD = "Setup/Wizard"


def _registry(request: Request):
    return getattr(request.app.state.sm, "setup_registry", None)


async def _require_setup_mode(request: Request) -> None:
    """404 unless the install still has incomplete required setup steps."""
    registry = _registry(request)
    if not registry or not await registry.incomplete(request.app):
        raise HTTPException(status_code=404)


# Setup mode first, CSRF second: on a configured install every /setup route
# answers 404 — the wizard does not exist there — rather than a 403 that
# advertises a live endpoint behind a missing token.
router = APIRouter(
    prefix="/setup",
    tags=["setup"],
    dependencies=[Depends(_require_setup_mode), Depends(RequiresCsrf())],
)


@router.get("", response_model=None)
@router.get("/", response_model=None)
async def setup_index(
    request: Request, inertia: InertiaDep, translator: TranslatorDep
) -> InertiaResponse:
    """The wizard itself: connection status, then every registered step."""
    registry = _registry(request)
    # incomplete_all, not incomplete: the latter only ever walks the *required*
    # steps, so an optional one would render with a checkmark whatever its
    # predicate says.
    pending = {s.id for s in await registry.incomplete_all(request.app)}

    return await inertia.render(
        _PAGE_WIZARD,
        {
            "checks": await connection_status(request),
            "steps": steps_payload(registry, pending, translator.t),
            "csrfToken": get_csrf_token(request),
        },
    )


@router.post("/test-connections")
async def test_connections(request: Request) -> dict:
    """Re-run the connection checks without reloading the page."""
    return {"checks": await connection_status(request)}


async def _read_form(request: Request) -> dict:
    """The submitted form as a dict; an empty body is an empty form."""
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Request body must be JSON.") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")
    return data


@router.post("/steps/{step_id}")
async def run_step_action(step_id: str, request: Request) -> dict:
    """Complete one step through the action its module registered.

    Order matters: the wizard must be open at all (the router's 404, the same
    answer as every other /setup route on a configured install), the CSRF
    token must match (the router's 403), the step must
    exist and offer an action (404), and the step itself must still be pending
    (409). Only then is the module's handler called — and it remains
    responsible for re-checking inside its own transaction, since two requests
    can pass this check together.
    """
    registry = _registry(request)
    step = registry.get(step_id)
    if step is None or step.action is None:
        raise HTTPException(status_code=404)
    if not await registry.is_pending(request.app, step):
        raise HTTPException(status_code=409, detail="This setup step is already complete.")

    data = await _read_form(request)
    result = await step.action.handler(request, data)
    logger.info("Setup: ran the action for step %s", step_id)
    return {"step": step_id, "result": result or {}}
