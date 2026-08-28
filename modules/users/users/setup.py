"""The setup step that gates a fresh install: does an administrator exist?

Registered by the local-accounts provider specifically, not by the host. An
install using Keycloak has its identities in Keycloak and a legitimately empty
local users table, so a host-level superuser count would hold those installs
behind a setup wizard forever. Keycloak registers no step; the gate never
engages there.
"""

from __future__ import annotations

import logging

from simple_module_core.setup_steps import SetupStep
from sqlalchemy import func, select

from users.models import User

logger = logging.getLogger(__name__)

STEP_ADMINISTRATOR = "users.administrator"


def build_admin_step() -> SetupStep:
    """The step that holds the app behind the wizard until an admin exists."""
    return SetupStep(
        id=STEP_ADMINISTRATOR,
        title="Create an administrator",
        description="An account that can sign in and manage this install.",
        is_complete=has_administrator,
        order=30,
    )


async def has_administrator(app) -> bool:
    """True once at least one active superuser exists.

    Counts ``is_active`` superusers: a deactivated admin cannot log in, so an
    install whose only administrator is disabled is as locked out as one with
    no administrator at all, and should be able to recover through the wizard.
    """
    session_factory = app.state.sm.db.session_factory
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.is_superuser.is_(True), User.is_active.is_(True))
        )
    return bool(count)
