"""Build auth lifecycle events from validated session identities."""

from contextlib import suppress
from uuid import UUID

from simple_module_core.user_events import UserLoggedOut

from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_SESSION


def session_logout_event(user: UserContext | None, *, local_account: bool) -> UserLoggedOut | None:
    """Capture the identity of the browser session that logout will end.

    The caller must validate the session independently of any bearer principal.
    Convert Users account IDs to UUIDs. Keep external providers' principal IDs
    as strings, including cache IDs and any case-sensitive subject fallback.
    """
    if user is None or user.auth_kind != AUTH_KIND_SESSION:
        return None
    user_id: UUID | str = user.id
    if local_account:
        with suppress(ValueError):
            user_id = UUID(user.id)
    email = user.email if isinstance(user.email, str) and user.email != "None" else ""
    return UserLoggedOut(user_id=user_id, email=email)
