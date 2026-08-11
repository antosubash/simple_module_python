"""Bulk invite — one submit, many addresses.

The invite form took a single address, so onboarding a team meant repeating
the same form once per person. This accepts a pasted list and reports each
address separately: one already-registered address in a list of twenty must
not discard the other nineteen.
"""

from __future__ import annotations

import contextlib
import logging

from fastapi import APIRouter, Depends, Request
from pydantic import EmailStr, TypeAdapter, ValidationError
from simple_module_core.events import EventBus
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from users.admin.service import UserService
from users.contracts.events import UserInvited
from users.contracts.schemas import BulkInviteResponse, BulkInviteResult, UserBulkInvite
from users.deps import get_event_bus, get_mailer, get_user_service

logger = logging.getLogger(__name__)

bulk_router = APIRouter()

STATUS_SENT = "sent"
STATUS_LINK = "link"
STATUS_FAILED = "failed"

MAX_ADDRESSES = 100
"""Enough for a team, small enough that one submit cannot mint an unbounded
number of live invite tokens."""

_EMAIL = TypeAdapter(EmailStr)
"""Per-address validation. Deliberately not a ``list[EmailStr]`` on the request
model: pydantic would reject the whole body over one typo, and the caller would
get a 422 naming an index rather than the per-address outcomes this endpoint
exists to produce."""


def _invite_link(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/users/invite/accept?token={token}"


@bulk_router.post("/invite/bulk", response_model=BulkInviteResponse)
async def admin_bulk_invite(
    data: UserBulkInvite,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
    # The same request-scoped session the service was built from, taken through
    # the dependency rather than off the service's private attribute.
    db: AsyncSession = Depends(get_db),
    mailer=Depends(get_mailer),
) -> BulkInviteResponse:
    """Invite every address in *data*, all sharing the same roles."""
    invited_by = getattr(request.state, "user", None)
    invited_by_name = invited_by.name if invited_by else "Administrator"

    # Absent attribute means "assume it delivers" — a third-party mailer must
    # never leak invite tokens into the response just by not declaring itself.
    delivers = getattr(mailer, "delivers_email", True)

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
            user, token = await service.invite(email, None, data.role_names, invited_by=invited_by)
            # Make this invite durable before touching the session again. The
            # failure path below rolls back, and the role rows the service
            # flushed but did not commit would go with it — leaving the person
            # invited with none of the roles the admin picked.
            await db.commit()
        except Exception as exc:
            # Already-registered is the common case and reads fine as-is;
            # anything else is logged so the admin's summary stays short.
            logger.info("bulk invite failed for %s: %s", email, exc)
            results.append(BulkInviteResult(email=email, status=STATUS_FAILED, detail=str(exc)))
            # Clear any failed transaction state before touching the session
            # again. A real DB error (an IntegrityError from a concurrent
            # signup, say) otherwise leaves every remaining address dying with
            # PendingRollbackError — one bad row turning into total failure,
            # the opposite of the partial success this endpoint promises.
            # Safe to discard: every successful invite above is committed
            # before the next one starts, so nothing durable is pending here.
            with contextlib.suppress(Exception):
                await db.rollback()
            continue

        if delivers:
            try:
                await mailer.send_invite(user.email, token, invited_by_name)
            except Exception as exc:
                # The account exists and the token is valid — the delivery
                # failed. Handing back the link turns a dead end into a
                # copy-paste, rather than stranding a half-finished invite.
                logger.warning("invite mail failed for %s: %s", email, exc)
                results.append(
                    BulkInviteResult(
                        email=email,
                        status=STATUS_LINK,
                        detail=str(exc),
                        link=_invite_link(request, token),
                    )
                )
            else:
                results.append(BulkInviteResult(email=email, status=STATUS_SENT))
        else:
            results.append(
                BulkInviteResult(
                    email=email,
                    status=STATUS_LINK,
                    link=_invite_link(request, token),
                )
            )

        await bus.publish(
            UserInvited(
                user_id=user.id,
                email=user.email,
                invited_by=(str(invited_by.id) if invited_by else None),
            )
        )

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
