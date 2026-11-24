"""Build auth lifecycle events from the current authenticated principal."""

from uuid import UUID

from simple_module_core.user_events import UserLoggedOut
from starlette.requests import Request

from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_SESSION


def session_logout_event(request: Request, *, local_account: bool) -> UserLoggedOut | None:
    """Capture the identity of the browser session that logout will end.

    *local_account* says the principal id is a local account UUID (the users
    module). An external IdP subject (Keycloak, OIDC) stays the original,
    case-sensitive string, even when it happens to look like a UUID.
    """
    user: UserContext | None = getattr(request.state, "user", None)
    if user is None or user.auth_kind != AUTH_KIND_SESSION:
        return None
    user_id: UUID | str = user.id
    if local_account:
        try:
            user_id = UUID(user.id)
        except ValueError:
            user_id = user.id
    return UserLoggedOut(user_id=user_id, email=user.email)
