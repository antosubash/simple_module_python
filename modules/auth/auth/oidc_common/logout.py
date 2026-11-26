"""Capture logout events through the native OIDC session validator."""

import logging
from typing import Any

from simple_module_core.user_events import UserLoggedOut
from starlette.requests import Request

from auth.contracts.events import session_logout_event

logger = logging.getLogger(__name__)


async def logout_event_for(request: Request, provider: Any) -> UserLoggedOut | None:
    """Capture a locally valid session without renewal, tolerating validation failures."""
    try:
        # The host's swappable AuthProvider need not expose session validation.
        state = getattr(request.app.state, provider.name)
        validator = provider(state=state)
        validator.jwks_cache = state.jwks_cache
        session_user = await validator.resolve_session(request, renew=False)
        return session_logout_event(session_user, local_account=False)
    except Exception as exc:
        # Event capture must not stop logout cleanup or expose exception details.
        logger.warning("Logout session validation failed (%s); skipping event", type(exc).__name__)
        return None
