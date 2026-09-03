"""Send a pending invitation again, from the row that is still waiting.

An invite that never arrived is the commonest reason a row sits in the
"invited" state forever, and the only previous cure was deleting the account
and starting over — which loses the roles the admin already assigned. This
mints a fresh token against the same account and moves ``invited_at`` forward,
so the row's "expires in 5d" describes the mail that was just sent.

Its own module rather than another block in ``api.py``: that file is at the
300-line cap, and this shares the delivery-vs-copy-a-link decision with
``bulk_invite`` rather than with the CRUD endpoints.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status

from users.admin.bulk_invite import STATUS_LINK, STATUS_SENT, invite_link
from users.admin.service import UserService
from users.contracts.schemas import BulkInviteResult
from users.deps import get_mailer, get_user_service
from users.exceptions import AlreadyVerifiedError, UserNotFoundError

logger = logging.getLogger(__name__)

resend_router = APIRouter()


@resend_router.post(
    "/{user_id}/resend-invite",
    response_model=BulkInviteResult,
    status_code=http_status.HTTP_202_ACCEPTED,
)
async def admin_resend_invite(
    user_id: uuid.UUID,
    request: Request,
    service: UserService = Depends(get_user_service),
    mailer=Depends(get_mailer),
) -> BulkInviteResult:
    """Re-issue the invitation for a pending account.

    202 rather than 200: the account was already updated, but whether the mail
    reaches anyone is the mailer's business and not something this response can
    promise. The body reports which of the two actually happened, reusing the
    bulk form's per-address shape so the admin screens read one result type.
    """
    actor = getattr(request.state, "user", None)
    try:
        user, token = await service.resend_invite(user_id, invited_by=actor)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    except AlreadyVerifiedError:
        raise HTTPException(
            status_code=409,
            detail="This account has already accepted its invitation.",
        ) from None

    # Absent attribute means "assume it delivers" — a third-party mailer must
    # never leak an invite token into the response just by not declaring
    # itself. No mailer at all delivers nothing, though.
    delivers = mailer is not None and getattr(mailer, "delivers_email", True)
    invited_by_name = getattr(actor, "name", None) or "Administrator"

    if delivers:
        try:
            await mailer.send_invite(user.email, token, invited_by_name)
        except Exception as exc:
            # The token is valid and the account is waiting; only delivery
            # failed. Handing back the link turns a dead end into a copy-paste.
            logger.warning("invite resend mail failed for %s: %s", user.email, exc)
            return BulkInviteResult(
                email=user.email,
                status=STATUS_LINK,
                detail=str(exc),
                link=invite_link(request, token),
            )
        return BulkInviteResult(email=user.email, status=STATUS_SENT)

    return BulkInviteResult(
        email=user.email,
        status=STATUS_LINK,
        link=invite_link(request, token),
    )
