"""Password-login lockout that holds across workers, source IPs and restarts.

Both password logins — the session ``/auth/login`` and the bearer
``/auth/token`` — go through here (GH #530). Two tiers:

* **Account lock**, on ``users_user``. A failure bumps ``failed_login_count``
  with one atomic ``UPDATE … RETURNING``, restarting at 1 once the last failure
  is older than the window, so every worker shares one count. Reaching
  ``login_lockout_account_failures`` stamps ``locked_until`` through the ORM —
  that is what puts the lock in the audit log. While it holds, every password
  login for the account is refused, the right password included.
* **Source throttle**, on the host's rate-limit store (Redis when configured).
  ``login:ip:<ip>:<username>`` stops one source after
  ``login_rate_limit_failures``; ``login:acct:<username>`` counts failures for a
  username with *no* account against the account threshold, so a 429 says
  nothing about whether the account exists.

Only failures count. The caller refuses with :func:`refused_for` first, then
records the outcome.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request, status
from simple_module_core.rate_limit import RateSpec, WindowStore
from sqlalchemy import case, func, select, update

from users.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from users.settings import UsersSettings

LOCKED_DETAIL = "Too many attempts — try again later"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class LoginAttempt:
    """One password login: who, from where, against which store, and when."""

    username: str
    ip: str
    store: WindowStore
    settings: UsersSettings
    now: datetime

    @classmethod
    def build(
        cls,
        username: str,
        ip: str,
        store: WindowStore,
        settings: UsersSettings,
        now: datetime,
    ) -> LoginAttempt:
        # Normalised once, here: ``Alice@x `` and ``alice@x`` are one account
        # to the user lookup, so they must be one counter too.
        return cls(username.strip().lower(), ip, store, settings, now)

    @property
    def ip_key(self) -> str:
        return f"login:ip:{self.ip}:{self.username}"

    @property
    def account_key(self) -> str:
        return f"login:acct:{self.username}"

    @property
    def ip_spec(self) -> RateSpec:
        s = self.settings
        return RateSpec(s.login_rate_limit_failures, s.login_rate_limit_window_seconds)

    @property
    def account_spec(self) -> RateSpec:
        s = self.settings
        return RateSpec(s.login_lockout_account_failures, s.login_rate_limit_window_seconds)

    def store_checks(self) -> Iterator[tuple[str, RateSpec]]:
        yield self.ip_key, self.ip_spec
        yield self.account_key, self.account_spec


def login_attempt(request: Request, username: str) -> LoginAttempt:
    """The :class:`LoginAttempt` for *username* arriving on *request*."""
    return LoginAttempt.build(
        username,
        request.client.host if request.client else "unknown",
        request.app.state.sm.rate_limit_store,
        request.app.state.users.settings,
        _utcnow(),
    )


def _by_username(username: str) -> Any:
    # The same predicate ``UserDatabaseWithRoles.get_by_email`` signs in with.
    return func.lower(User.email) == username


async def refused_for(session: AsyncSession, attempt: LoginAttempt) -> int | None:
    """Seconds the caller must wait, or ``None`` when the attempt may proceed."""
    waits: list[int] = []
    stmt = select(User.locked_until).where(_by_username(attempt.username))
    for locked_until in (await session.execute(stmt)).scalars():
        if locked_until is not None and locked_until > attempt.now:
            waits.append(math.ceil((locked_until - attempt.now).total_seconds()))
    for key, spec in attempt.store_checks():
        result = await attempt.store.peek(key, spec)
        if not result.allowed:
            waits.append(result.retry_after)
    return max(waits) if waits else None


async def record_failure(session: AsyncSession, attempt: LoginAttempt) -> None:
    """Count a failed password login in both tiers, locking at the threshold.

    Commits *session*: the caller answers by raising, and the request's unit
    of work rolls back on that path — the count has to be durable before then.
    The request has only read by this point, so nothing else is committed.
    """
    s = attempt.settings
    await attempt.store.hit(attempt.ip_key, attempt.ip_spec)
    window_start = attempt.now - timedelta(seconds=s.login_rate_limit_window_seconds)
    stale = User.last_failed_login_at.is_(None) | (User.last_failed_login_at < window_start)
    stmt = (
        update(User)
        .where(_by_username(attempt.username))
        .values(
            failed_login_count=case((stale, 1), else_=User.failed_login_count + 1),
            last_failed_login_at=attempt.now,
            # A failed sign-in is not an edit of the account.
            updated_at=User.updated_at,
        )
        .returning(User.id, User.failed_login_count)
        .execution_options(synchronize_session=False)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        await attempt.store.hit(attempt.account_key, attempt.account_spec)
    for user_id, count in rows:
        if count >= s.login_lockout_account_failures:
            # Through the ORM, not the UPDATE above, so the audit log records it.
            user = await session.get(User, user_id, populate_existing=True)
            if user is not None:
                cooldown = timedelta(seconds=s.login_rate_limit_cooldown_seconds)
                user.locked_until = attempt.now + cooldown
                user.failed_login_count = 0
    await session.commit()


async def record_success(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Clear the account's failure count. Rides the request's own commit."""
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .where((User.failed_login_count != 0) | User.last_failed_login_at.is_not(None))
        .values(failed_login_count=0, last_failed_login_at=None, updated_at=User.updated_at)
        .execution_options(synchronize_session=False)
    )


def too_many_attempts(retry_after: int) -> HTTPException:
    """The 429 for a locked account or a throttled source — deliberately identical."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=LOCKED_DETAIL,
        headers={"Retry-After": str(max(1, retry_after))},
    )
