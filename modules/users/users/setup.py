"""The setup step that gates a fresh install: does any local account exist?

Registered by the local-accounts provider specifically, not by the host. An
install using Keycloak has its identities in Keycloak and a legitimately empty
local users table, so a host-level administrator count would hold those installs
behind a setup wizard forever. Keycloak registers no step; the gate never
engages there.

The step is complete as soon as *any* local account exists, not only an
administrator: the wizard's action creates the first account of an empty
install and refuses once one exists, so an install that has accounts but has
lost its last administrator (deactivated outside the admin UI) must not be held
behind a wizard it cannot finish. It recovers through
``smpy users create-admin`` instead.
"""

from __future__ import annotations

import logging

from simple_module_core.setup_steps import SetupAction, SetupField, SetupStep
from sqlalchemy import select

from users.models import User

logger = logging.getLogger(__name__)

STEP_ADMINISTRATOR = "users.administrator"


_KEY = "users.setup.administrator"

# Mirrors UserManager.validate_password's minimum so the browser refuses the
# obvious case before a round trip; the server enforces the real policy.
_MIN_PASSWORD_LENGTH = 8


def _admin_action() -> SetupAction:
    """The wizard form that completes the step — see ``users.setup_action``."""
    # Imported lazily: ``users.setup_action`` imports this module for
    # ``session_has_local_account``, so a top-level import would be circular.
    from users.setup_action import create_first_administrator

    return SetupAction(
        handler=create_first_administrator,
        fields=[
            SetupField(
                name="email",
                label="Email",
                label_key=f"{_KEY}.email",
                type="email",
                autocomplete="email",
            ),
            SetupField(
                name="password",
                label="Password",
                label_key=f"{_KEY}.password",
                type="password",
                autocomplete="new-password",
                min_length=_MIN_PASSWORD_LENGTH,
            ),
            SetupField(
                name="full_name",
                label="Full name",
                label_key=f"{_KEY}.full_name",
                required=False,
                autocomplete="name",
            ),
        ],
        submit_label="Create administrator",
        submit_label_key=f"{_KEY}.submit",
    )


def build_admin_step() -> SetupStep:
    """The step that holds an empty install behind the wizard until it has an account."""
    return SetupStep(
        id=STEP_ADMINISTRATOR,
        title="Create an administrator",
        title_key=f"{_KEY}.title",
        description="An account that can sign in and manage this install.",
        description_key=f"{_KEY}.description",
        is_complete=has_local_account,
        order=30,
        action=_admin_action(),
    )


async def session_has_local_account(session) -> bool:
    """True when *session* sees any local account (the step's and the action's rule)."""
    return await session.scalar(select(User.id).limit(1)) is not None


async def has_local_account(app) -> bool:
    """True once any local account exists; the step's completion predicate."""
    session_factory = app.state.sm.db.session_factory
    async with session_factory() as session:
        return await session_has_local_account(session)
