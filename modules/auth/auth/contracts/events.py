"""Build auth lifecycle events from the current authenticated principal."""

from contextlib import suppress
from uuid import UUID

from simple_module_core.user_events import UserLoggedOut
from starlette.requests import Request

from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_SESSION


def session_logout_event(request: Request, *, local_account: bool) -> UserLoggedOut | None:
    """Capture the identity of the browser session that logout will end.

    Convert Users account IDs to UUIDs. Keep external providers' principal IDs
    as strings, including cache IDs and any case-sensitive subject fallback.
    """
    user: UserContext | None = getattr(request.state, "user", None)
    if user is None or user.auth_kind != AUTH_KIND_SESSION:
        return None
    user_id: UUID | str = user.id
    if local_account:
        with suppress(ValueError):
            user_id = UUID(user.id)
    # Session deserialization stringifies a null Keycloak email.
    email = user.email if isinstance(user.email, str) and user.email != "None" else ""
    return UserLoggedOut(user_id=user_id, email=email)
