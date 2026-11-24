"""Build auth lifecycle events from the current authenticated principal."""

from uuid import UUID

from simple_module_core.user_events import UserLoggedOut
from starlette.requests import Request

from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_SESSION


def session_logout_event(request: Request) -> UserLoggedOut | None:
    """Capture the identity of the browser session that logout will end."""
    user: UserContext | None = getattr(request.state, "user", None)
    if user is None or user.auth_kind != AUTH_KIND_SESSION:
        return None
    try:
        user_id: UUID | str = UUID(user.id)
    except ValueError:
        # An OIDC provider can supply a subject without a local account ID.
        user_id = user.id
    return UserLoggedOut(user_id=user_id, email=user.email)
