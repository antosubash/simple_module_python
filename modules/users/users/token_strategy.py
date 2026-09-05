"""Access-token strategy that bounds each row instead of the whole process.

fastapi-users' ``DatabaseStrategy`` carries one ``lifetime_seconds`` for every
token it reads, and ``current_user`` resolves its strategy from the shared
backend — so the number cannot vary per request. That forced the read window up
to the widest thing any sign-in asks for (thirty days, for "keep me signed in"),
and every other credential inherited it: an ordinary sign-in wrote an ``sm_auth``
cookie whose browser ``Max-Age`` said fourteen days while the row behind it was
accepted for thirty, and ``/api/users/auth/token`` returned
``expires_in=900`` for a row good for a month.

The read window stays wide — it is the ceiling the deployment will ever accept —
and each row now carries the deadline it was actually minted for, plus the
``session_version`` it was minted under. Both are enforced here, so the two
bearer paths agree: this strategy backs ``fastapi_users.current_user``, and
``UsersAuthProvider._resolve_bearer`` applies the same two clauses in SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi_users import exceptions, models
from fastapi_users.authentication.strategy.db import AccessTokenDatabase, DatabaseStrategy
from fastapi_users.manager import BaseUserManager

from users.models import UserAccessToken


def token_is_live(access_token: UserAccessToken, user: Any, now: datetime | None = None) -> bool:
    """Whether this row still authenticates ``user``.

    The one definition of "live", shared by the two bearer read paths so they
    cannot drift: past its own deadline, or minted under a superseded
    ``session_version``, and the credential is spent.
    """
    now = now or datetime.now(UTC)
    expires_at = access_token.expires_at
    if expires_at is not None:
        # SQLite hands back naive datetimes for a TIMESTAMPAware column; treat
        # them as UTC rather than raising on the comparison.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            return False
    return int(access_token.session_version or 0) == int(getattr(user, "session_version", 0) or 0)


class ExpiringDatabaseStrategy(DatabaseStrategy):
    """``DatabaseStrategy`` that stamps and honours a per-row deadline.

    ``read_ceiling_seconds`` is the inherited ``lifetime_seconds`` — the oldest
    row the query will even look at. ``mint_lifetime_seconds`` is what *this*
    sign-in asked for, and is what lands in ``expires_at``.
    """

    def __init__(
        self,
        database: AccessTokenDatabase[UserAccessToken],
        *,
        read_ceiling_seconds: int,
        mint_lifetime_seconds: int,
    ) -> None:
        super().__init__(database, lifetime_seconds=read_ceiling_seconds)
        self.mint_lifetime_seconds = mint_lifetime_seconds

    def _create_access_token_dict(self, user: models.UP) -> dict[str, Any]:
        data = super()._create_access_token_dict(user)
        data["expires_at"] = datetime.now(UTC) + timedelta(seconds=self.mint_lifetime_seconds)
        data["session_version"] = int(getattr(user, "session_version", 0) or 0)
        return data

    async def read_token(
        self, token: str | None, user_manager: BaseUserManager[models.UP, models.ID]
    ) -> models.UP | None:
        """Resolve a token, refusing one that is past its deadline or stranded.

        Reimplemented rather than wrapping ``super()``: the base returns the user
        and drops the row, and re-fetching it to check two columns would double
        the queries on the hot path.
        """
        if token is None:
            return None

        max_age = None
        if self.lifetime_seconds:
            max_age = datetime.now(UTC) - timedelta(seconds=self.lifetime_seconds)

        access_token = await self.database.get_by_token(token, max_age)
        if access_token is None:
            return None

        try:
            parsed_id = user_manager.parse_id(access_token.user_id)
            user = await user_manager.get(parsed_id)
        except (exceptions.UserNotExists, exceptions.InvalidID):
            return None

        if not token_is_live(access_token, user):
            return None
        return user
