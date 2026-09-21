"""``POST /api/users/auth/demo/{role}`` — sign in as a shared demo account.

Its own module rather than a branch inside ``api.login``: there is no password
in the request, so none of the rate-limit-on-failure, verification or
"remember me" machinery applies. What it shares with the password path is the
session bridging, and that is three lines.

``role`` in the path rather than a body field so each account gets its own
throughput budget (the limiter keys on path + client IP) and so switching
between the two is a plain link's worth of work. No password reaches the
browser either way: a visitor clicks a button, the server looks the account up
itself, and the session it mints is stamped :data:`users.demo.SESSION_DEMO_KEY`
so :class:`users.demo_guard.DemoReadOnlyMiddleware` can recognise it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi_users import exceptions as fu_exceptions
from simple_module_core.redirect_safety import SESSION_NEXT_KEY

from users.auth_local.rate_limit import enforce_auth_throughput_limit
from users.constants import ADMIN_ROLE_NAME, SESSION_USER_ID_KEY, USER_ROLE_NAME
from users.demo import SESSION_DEMO_KEY, resolve_demo_account
from users.deps import auth_backend, get_user_manager
from users.manager import UserManager

logger = logging.getLogger("users.demo")

router = APIRouter()

# Spelled as a literal rather than derived from the role constants: this is a
# URL segment, and a rename of the internal role name must not silently change
# the public route. ``{role}` is constrained here so an unknown value 404s in
# routing rather than reaching the handler.
_DEMO_ROLE_PATH = "/auth/demo/{role}"
_KNOWN_ROLES = frozenset({ADMIN_ROLE_NAME, USER_ROLE_NAME})


@router.post(
    _DEMO_ROLE_PATH,
    status_code=204,
    # Every call mints an access-token row and a session cookie, and the
    # endpoint takes no credential — without a budget it is a free row
    # generator for anyone who finds the showcase instance. Keyed on path, so
    # the two accounts get independent budgets and a bot hammering one cannot
    # lock a visitor out of the other.
    dependencies=[Depends(enforce_auth_throughput_limit)],
)
async def demo_login(
    role: str,
    request: Request,
    response: Response,
    user_manager: UserManager = Depends(get_user_manager),
    strategy=Depends(auth_backend.get_strategy),
) -> Response:
    """Sign the caller in as the demo account for ``role``.

    404 rather than 403 for every failure here — demo mode off, this account
    not configured, an unknown role — matching ``/users/register``: a disabled
    feature should look absent, not forbidden, so probing says nothing about
    how the instance is configured.
    """
    if role not in _KNOWN_ROLES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    account = resolve_demo_account(request.app.state.users.settings, role)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # By email, not by a cached id: the ids on app state are a boot-time
    # convenience, so a worker whose reconcile failed would otherwise serve a
    # button that 500s. Through the manager rather than a session of our own
    # so the row ``on_after_login`` writes ``last_login_at`` to is this one.
    try:
        demo_user = await user_manager.get_by_email(account.email)
    except fu_exceptions.UserNotExists:
        logger.warning("users.demo.missing_account", extra={"email": account.email, "role": role})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
    if not demo_user.is_active or demo_user.disabled_at is not None:
        logger.warning("users.demo.inactive_account", extra={"email": account.email, "role": role})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await user_manager.on_after_login(demo_user, request, response)
    login_response = await auth_backend.login(strategy, demo_user)
    request.session[SESSION_USER_ID_KEY] = str(demo_user.id)
    request.session[SESSION_DEMO_KEY] = True
    # A demo visitor bounced off a deep link should land there, same as any
    # other sign-in; clearing it here keeps the next plain visit to the login
    # page from inheriting a stale destination.
    request.session.pop(SESSION_NEXT_KEY, None)
    return login_response
