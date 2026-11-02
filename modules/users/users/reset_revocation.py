"""Revoke credentials in the same commit as a password reset (#686)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request

from users.credentials import announce_revocation, revoke_credential_rows
from users.models import User

logger = logging.getLogger(__name__)


class ResetRevocationMixin:
    """Make a mailbox reset and the revocation it implies one transaction.

    fastapi-users' ``reset_password`` writes the new hash through
    ``user_db.update``, which commits, and only then calls
    ``on_after_reset_password``. Revoking there would leave a window where the
    new password is durable but every old session and token still works (and
    stays working if that second write fails). So the rows are revoked inside
    ``_update``, flushed into the very commit that stores the password, and the
    cached counters are evicted right after it returns — the data is durable by
    then, and the request's own final commit may have nothing left to write
    (which would discard ``on_commit`` callbacks).
    """

    _reset_request: Request | None = None
    _resetting: bool = False

    async def reset_password(self, token: str, password: str, request: Request | None = None):
        self._resetting, self._reset_request = True, request
        try:
            return await super().reset_password(token, password, request)
        finally:
            self._resetting, self._reset_request = False, None

    async def _update(self, user: User, update_dict: dict[str, Any]) -> User:
        if not (self._resetting and update_dict.get("password") is not None):
            return await super()._update(user, update_dict)
        await revoke_credential_rows(self.user_db.session, user)
        updated = await super()._update(user, update_dict)
        request = self._reset_request
        try:
            await announce_revocation(request.app if request is not None else None, user.id)
        except Exception:
            # The reset is durable; like an on_commit callback, a failed eviction
            # is logged (cached counters still expire on their TTL) rather than
            # turning a completed reset into a 500.
            logger.exception("users.reset.revocation_announce_failed")
        return updated
