"""Compose first-run steps without depending on the contributing module."""

import logging

from fastapi import Request
from simple_module_core.modules.app_state import get_migration_status
from simple_module_core.web.setup_steps import SetupStep

from simple_module_hosting.setup_gate import STEP_MIGRATIONS, is_first_run

logger = logging.getLogger(__name__)


async def migration_follow_up(request: Request) -> SetupStep | None:
    """The next required step may opt in, only on a verified never-migrated DB.

    Do not use ordinary pending evaluation here: missing tables count as
    complete there to avoid exposing actions on a configured install's DB error.
    """
    if not await is_first_run(request.app, get_migration_status(request.app)):
        return None
    steps = request.app.state.sm.setup_registry.required_steps
    for index, step in enumerate(steps[:-1]):
        if step.id == STEP_MIGRATIONS:
            following = steps[index + 1]
            if following.action and following.action.validate_before_migrations:
                return following
    return None


async def run_follow_up(request: Request, step: SetupStep, data: dict) -> bool:
    """Return whether recovery is needed; never invoke a completed step."""
    registry = request.app.state.sm.setup_registry
    if not await registry.is_pending(request.app, step):
        return False
    try:
        await step.action.handler(request, data)
    except Exception:
        # Migrations have committed. Return to the remaining form with a safe
        # message, keeping exception details and credentials out of the cookie.
        logger.exception("Setup: follow-up step %s failed after migrations", step.id)
        # The handler may have committed before a final refresh failed.
        if not await registry.is_pending(request.app, step):
            return False
        request.session["setup_error"] = {"step": step.id}
        return True
    return False
