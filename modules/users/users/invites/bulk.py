"""Bulk invite — one submit, many addresses.

The invite form took a single address, so onboarding a team meant repeating
the same form once per person. This accepts a pasted list and reports each
address separately: one already-registered address in a list of twenty must
not discard the other nineteen.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi_users.exceptions import UserAlreadyExists
from pydantic import EmailStr, TypeAdapter, ValidationError
from simple_module_core.events import EventBus
from simple_module_db import independent_session

from users.admin.links import admin_link_base
from users.admin.safety import check_request_role_assignment
from users.admin.service import UserService
from users.contracts.events import UserInvited
from users.contracts.schemas import BulkInviteResponse, BulkInviteResult, UserBulkInvite
from users.db_adapter import UserDatabaseWithRoles
from users.deps import get_event_bus, get_mailer
from users.mailer import mailer_delivers
from users.manager import UserManager
from users.models import OAuthAccount, User

logger = logging.getLogger(__name__)

bulk_router = APIRouter()

STATUS_SENT = "sent"
STATUS_LINK = "link"

MAILER_FAILURE_DETAIL = "The invitation could not be emailed — use the link instead."
"""What an admin is told when delivery fails.

Deliberately not ``str(exc)``: an SMTP error quotes the host, the port and
sometimes the credential it tried, and this response is rendered straight
into an admin screen. The real message goes to the log, where it is one
correlation id away and not on anybody's screenshot."""
STATUS_FAILED = "failed"

MAX_ADDRESSES = 100
"""Enough for a team, small enough that one submit cannot mint an unbounded
number of live invite tokens."""

_EMAIL = TypeAdapter(EmailStr)
"""Per-address validation. Deliberately not a ``list[EmailStr]`` on the request
model: pydantic would reject the whole body over one typo, and the caller would
get a 422 naming an index rather than the per-address outcomes this endpoint
exists to produce."""


def _failure_detail(exc: Exception) -> str:
    """Only known errors have specific messages; backend details stay in logs."""
    if isinstance(exc, UserAlreadyExists):
        return "Already a member of this workspace"
    return "The invitation could not be created. Please try again."


def invite_link(request: Request, token: str) -> str:
    """Build the accept URL the admin will hand to the invitee.

    Surfaced only when mail could not be delivered, i.e. exactly when the admin
    has to pass it on by hand. The origin follows :func:`admin_link_base`.
    """
    base = admin_link_base(request)
    return f"{base}/users/invite/accept?token={token}"


@bulk_router.post("/invite/bulk", response_model=BulkInviteResponse)
async def admin_bulk_invite(
    data: UserBulkInvite,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    mailer=Depends(get_mailer),
) -> BulkInviteResponse:
    """Invite every address in *data*, all sharing the same roles."""
    invited_by = getattr(request.state, "user", None)
    await check_request_role_assignment(request, data.role_names)
    invited_by_name = invited_by.name if invited_by else "Administrator"

    # Same question the page's ``mailer_delivers`` prop answers, asked once.
    delivers = mailer_delivers(mailer)

    # Preserve submit order but drop repeats: pasting a list with the same
    # address twice should not create two invites for it. A malformed address
    # is reported like any other per-address failure rather than rejecting the
    # submit — a typo in one line of a pasted column must not lose the column.
    seen: set[str] = set()
    ordered: list[str] = []
    malformed: list[str] = []
    for raw in data.emails:
        email = str(raw).strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        try:
            _EMAIL.validate_python(email)
        except ValidationError:
            malformed.append(email)
            continue
        ordered.append(email)

    # Anything past the cap is reported, never silently dropped: truncating in
    # silence tells the admin "100 invites sent" while 50 people are never
    # contacted, and nothing on screen says otherwise.
    accepted, overflow = ordered[:MAX_ADDRESSES], ordered[MAX_ADDRESSES:]

    results: list[BulkInviteResult] = []
    for email in accepted:
        try:
            async with independent_session(request.app) as checkpoint:
                manager = UserManager(
                    UserDatabaseWithRoles(checkpoint, User, OAuthAccount),
                    mailer,
                    request.app.state.users.settings,
                )
                service = UserService(
                    checkpoint, manager, request.app, actor=invited_by, request=request
                )
                user, token = await service.invite(
                    email, None, data.role_names, invited_by=invited_by
                )
            # The invite and roles are durable before delivery or event handlers.
        except Exception as exc:
            # Already-registered is the common case and reads fine as-is;
            # anything else is logged so the admin's summary stays short.
            logger.info("bulk invite failed for %s: %s", email, exc)
            results.append(
                BulkInviteResult(email=email, status=STATUS_FAILED, detail=_failure_detail(exc))
            )
            continue

        if delivers:
            try:
                await mailer.send_invite(user.email, token, invited_by_name, data.message)
            except Exception:
                # The account exists and the token is valid — the delivery
                # failed. Handing back the link turns a dead end into a
                # copy-paste, rather than stranding a half-finished invite.
                logger.exception("invite mail failed for %s", email)
                results.append(
                    BulkInviteResult(
                        email=email,
                        status=STATUS_LINK,
                        detail=MAILER_FAILURE_DETAIL,
                        link=invite_link(request, token),
                    )
                )
            else:
                results.append(BulkInviteResult(email=email, status=STATUS_SENT))
        else:
            results.append(
                BulkInviteResult(
                    email=email,
                    status=STATUS_LINK,
                    link=invite_link(request, token),
                )
            )

        await bus.publish(
            UserInvited(
                user_id=user.id,
                email=user.email,
                invited_by=(str(invited_by.id) if invited_by else None),
            )
        )
        # Handlers keep the request unit of work. Later invite failures roll
        # back only their independent session, so handler writes remain pending
        # for CommitBeforeResponseMiddleware and keep their on_commit ordering.

    results.extend(
        BulkInviteResult(
            email=email,
            status=STATUS_FAILED,
            detail="Not a valid email address",
        )
        for email in malformed
    )
    results.extend(
        BulkInviteResult(
            email=email,
            status=STATUS_FAILED,
            detail=f"Not attempted — over the {MAX_ADDRESSES}-address limit for one submit",
        )
        for email in overflow
    )

    return BulkInviteResponse(results=results)
