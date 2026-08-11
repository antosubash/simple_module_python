"""Bulk invite — one submit, many addresses.

The invite form took a single address, so onboarding a team meant repeating
the same form once per person. This accepts a pasted list and reports each
address separately: one already-registered address in a list of twenty must
not discard the other nineteen.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from simple_module_core.events import EventBus

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


def _invite_link(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/users/invite/accept?token={token}"


@bulk_router.post("/invite/bulk", response_model=BulkInviteResponse)
async def admin_bulk_invite(
    data: UserBulkInvite,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
    mailer=Depends(get_mailer),
) -> BulkInviteResponse:
    """Invite every address in *data*, all sharing the same roles."""
    invited_by = getattr(request.state, "user", None)
    invited_by_name = invited_by.name if invited_by else "Administrator"

    # Absent attribute means "assume it delivers" — a third-party mailer must
    # never leak invite tokens into the response just by not declaring itself.
    delivers = getattr(mailer, "delivers_email", True)

    # Preserve submit order but drop repeats: pasting a list with the same
    # address twice should not create two invites for it.
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in data.emails[:MAX_ADDRESSES]:
        email = str(raw).strip().lower()
        if email and email not in seen:
            seen.add(email)
            ordered.append(email)

    results: list[BulkInviteResult] = []
    for email in ordered:
        try:
            user, token = await service.invite(email, None, data.role_names, invited_by=invited_by)
        except Exception as exc:
            # Already-registered is the common case and reads fine as-is;
            # anything else is logged so the admin's summary stays short.
            logger.info("bulk invite failed for %s: %s", email, exc)
            results.append(BulkInviteResult(email=email, status=STATUS_FAILED, detail=str(exc)))
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

    return BulkInviteResponse(results=results)
