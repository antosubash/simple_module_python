"""Build auth lifecycle events from validated session identities."""

from contextlib import suppress
from uuid import UUID

from simple_module_core.runtime.deprecation import deprecate
from simple_module_core.user_events import UserLoggedOut
from starlette.requests import Request

from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_SESSION

_LEGACY_REQUEST = deprecate(
    "auth.contracts.events.session_logout_event(request)",
    remove_in="0.0.52",
    use="session_logout_event() with the validated session UserContext",
)


def session_logout_event(
    user: UserContext | Request | None = None,
    *,
    local_account: bool,
    request: Request | None = None,
) -> UserLoggedOut | None:
    """Capture the identity of the browser session that logout will end.

    The caller must validate the session independently of any bearer principal.
    Convert Users account IDs to UUIDs. Keep external providers' principal IDs
    as strings, including cache IDs and any case-sensitive subject fallback.
    Passing a Request (positionally or as request=) is supported until 0.0.52.
    """
    if request is not None:
        if user is not None:
            raise TypeError("Pass either user or request, not both")
        user = request
    if isinstance(user, Request):
        _LEGACY_REQUEST.warn()
        user = getattr(user.state, "user", None)
    if user is None or user.auth_kind != AUTH_KIND_SESSION:
        return None
    user_id: UUID | str = user.id
    if local_account:
        with suppress(ValueError):
            user_id = UUID(user.id)
    email = user.email if isinstance(user.email, str) and user.email != "None" else ""
    return UserLoggedOut(user_id=user_id, email=email)
