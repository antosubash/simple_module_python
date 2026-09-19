"""``POST /api/users/auth/demo`` — sign in as the shared demo account.

Its own module rather than a branch inside ``api.login``: there is no password
in the request, so none of the rate-limit-on-failure, verification or
"remember me" machinery applies. What it shares with the password path is the
session bridging, and that is three lines.

The account's password is never sent to the browser. A visitor clicks the
button, the server looks the account up itself, and the session it mints is
stamped :data:`users.demo.SESSION_DEMO_KEY` so
:class:`users.demo_guard.DemoReadOnlyMiddleware` can recognise it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi_users import exceptions as fu_exceptions
from simple_module_core.redirect_safety import SESSION_NEXT_KEY

from users.auth_local.rate_limit import enforce_auth_throughput_limit
from users.constants import SESSION_USER_ID_KEY
from users.demo import SESSION_DEMO_KEY, resolve_demo_account
from users.deps import auth_backend, get_user_manager
from users.manager import UserManager

logger = logging.getLogger("users.demo")

router = APIRouter()


@router.post(
    "/auth/demo",
    status_code=204,
    # Every call mints an access-token row and a session cookie, and the
    # endpoint takes no credential — without a budget it is a free row
    # generator for anyone who finds the showcase instance.
    dependencies=[Depends(enforce_auth_throughput_limit)],
)
async def demo_login(
    request: Request,
    response: Response,
    user_manager: UserManager = Depends(get_user_manager),
    strategy=Depends(auth_backend.get_strategy),
) -> Response:
    """Sign the caller in as the configured demo account.

    404 rather than 403 when demo mode is off, matching ``/users/register``:
    a disabled feature should look absent, not forbidden, so probing the
    endpoint says nothing about how the instance is configured.
    """
    state = request.app.state.users
    account = resolve_demo_account(state.settings)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # By email, not by the cached ``state.demo_user_id``: the id is a boot-time
    # convenience, so a worker whose reconcile failed would otherwise serve a
    # button that 500s. Through the manager rather than a session of our own
    # so the row ``on_after_login`` writes ``last_login_at`` to is this one.
    try:
        demo_user = await user_manager.get_by_email(account.email)
    except fu_exceptions.UserNotExists:
        logger.warning("users.demo.missing_account", extra={"email": account.email})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
    if not demo_user.is_active or demo_user.disabled_at is not None:
        logger.warning("users.demo.inactive_account", extra={"email": account.email})
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
