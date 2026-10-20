"""Password-login lockout that holds across workers, source IPs and restarts.

Both password logins — the session ``/auth/login`` and the bearer
``/auth/token`` — go through here (GH #530). Two tiers:

* **Account lock**, on ``users_user``. ``failed_login_count`` restarts at 1
  once the last failure is older than the window, so every worker shares one
  count. The attempt that reaches ``login_lockout_account_failures`` stamps
  ``locked_until`` through the ORM — that is what puts the lock in the audit
  log — and is itself answered with the 429. While the lock holds, every
  password login for the account is refused, the right password included.
* **Source throttle**, on the host's rate-limit store (Redis when configured):
  ``login:ip:<ip>:<username>`` admits ``login_rate_limit_failures`` attempts
  per window; a success clears it.

A username with *no* account is put through the same account rules on the
store instead (``login:acct:<username>`` counts on a sliding window, matching
the row's restart rule, and ``login:acct-lock:<username>`` holds the lock for
the cooldown), so its responses — status, detail, ``Retry-After``, the attempt
that trips, how long it lasts — are those of a real account.

**Counted before the password is checked.** :func:`admit` takes a slot in both
tiers first and refuses when there is none; :func:`record_success` gives it
back. Checking and counting in one step is what stops a parallel burst from
getting more password tries than the threshold: of N concurrent attempts,
exactly one can take the last slot.
"""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request, status
from simple_module_core.rate_limit import RateSpec, WindowStore
from sqlalchemy import case, func, select, update

from users.auth_local.rate_limit import client_ip
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
    def threshold(self) -> int:
        return self.settings.login_lockout_account_failures

    @property
    def cooldown(self) -> int:
        return self.settings.login_rate_limit_cooldown_seconds

    @property
    def key_name(self) -> str:
        """The username as it appears in store keys.

        The body limit is 10 MiB, so an unauthenticated caller could otherwise
        park a megabyte-long key in Redis per request. Anything longer than an
        address can be (254) is hashed; it matches no account either way.
        """
        if len(self.username) <= 254:
            return self.username
        return hashlib.sha256(self.username.encode()).hexdigest()

    @property
    def ip_key(self) -> str:
        return f"login:ip:{self.ip}:{self.key_name}"

    @property
    def ip_spec(self) -> RateSpec:
        s = self.settings
        return RateSpec(s.login_rate_limit_failures, s.login_rate_limit_window_seconds)

    @property
    def account_key(self) -> str:
        return f"login:acct:{self.key_name}"

    @property
    def lock_key(self) -> str:
        return f"login:acct-lock:{self.key_name}"

    @property
    def lock_spec(self) -> RateSpec:
        return RateSpec(1, self.cooldown)


@dataclass(frozen=True, slots=True)
class Admission:
    """A slot taken by :func:`admit`: the account rows it counted against and the count."""

    user_ids: tuple[uuid.UUID, ...]
    count: int


def login_attempt(request: Request, username: str) -> LoginAttempt:
    """The :class:`LoginAttempt` for *username* arriving on *request*."""
    return LoginAttempt.build(
        username,
        client_ip(request),
        request.app.state.sm.rate_limit_store,
        request.app.state.users.settings,
        _utcnow(),
    )


def too_many_attempts(retry_after: int) -> HTTPException:
    """The 429 for a locked account or a throttled source — deliberately identical."""
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=LOCKED_DETAIL,
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _by_username(username: str) -> Any:
    # The same predicate ``UserDatabaseWithRoles.get_by_email`` signs in with.
    return func.lower(User.email) == username


async def admit(session: AsyncSession, attempt: LoginAttempt) -> Admission:
    """Take a slot for this attempt in both tiers, or raise the 429.

    Commits *session* when it counts against an account row, so other workers
    see the slot taken before this one checks the password. The request has
    only read by this point, so nothing else is committed with it.
    """
    source = await attempt.store.hit(attempt.ip_key, attempt.ip_spec)
    if not source.allowed:
        raise too_many_attempts(source.retry_after)
    stmt = select(User.locked_until).where(_by_username(attempt.username))
    rows = list((await session.execute(stmt)).scalars().all())
    if rows:
        return await _admit_account(session, attempt, rows)
    return await _admit_unknown(attempt)


def _lock_remaining(locks: list[datetime | None], now: datetime) -> int | None:
    """Seconds until the latest live lock in *locks* lifts, or ``None`` if none holds."""
    live = [lock for lock in locks if lock is not None and lock > now]
    return math.ceil((max(live) - now).total_seconds()) if live else None


async def _admit_account(
    session: AsyncSession, attempt: LoginAttempt, locks: list[datetime | None]
) -> Admission:
    remaining = _lock_remaining(locks, attempt.now)
    if remaining is not None:
        raise too_many_attempts(remaining)
    window_start = attempt.now - timedelta(seconds=attempt.settings.login_rate_limit_window_seconds)
    stale = User.last_failed_login_at.is_(None) | (User.last_failed_login_at < window_start)
    stmt = (
        update(User)
        .where(_by_username(attempt.username))
        # Conditional, so checking for a free slot and taking it are one step:
        # a row that is locked, or whose last slot is already taken (its lock
        # is being written), is not counted again.
        .where(User.locked_until.is_(None) | (User.locked_until <= attempt.now))
        .where(stale | (User.failed_login_count < attempt.threshold))
        .values(
            failed_login_count=case((stale, 1), else_=User.failed_login_count + 1),
            last_failed_login_at=attempt.now,
            # A sign-in attempt is not an edit of the account.
            updated_at=User.updated_at,
        )
        .returning(User.id, User.failed_login_count)
        .execution_options(synchronize_session=False)
    )
    counted = (await session.execute(stmt)).all()
    await session.commit()
    if not counted:
        # Locked by another worker since the read above: report the time left,
        # as the unknown-username lock does, or ``Retry-After`` would tell the
        # two apart. Otherwise the last slot is taken and its lock is being
        # written — the full cooldown, as on the unknown path.
        stmt = select(User.locked_until).where(_by_username(attempt.username))
        locks = list((await session.execute(stmt)).scalars().all())
        raise too_many_attempts(_lock_remaining(locks, attempt.now) or attempt.cooldown)
    return Admission(tuple(row[0] for row in counted), max(row[1] for row in counted))


async def _admit_unknown(attempt: LoginAttempt) -> Admission:
    # The account rules above, replayed on the store for a username with no row.
    lock = await attempt.store.peek(attempt.lock_key, attempt.lock_spec)
    if not lock.allowed:
        raise too_many_attempts(lock.retry_after)
    account_spec = RateSpec(attempt.threshold, attempt.settings.login_rate_limit_window_seconds)
    counted = await attempt.store.hit(attempt.account_key, account_spec, sliding=True)
    if counted.count > attempt.threshold:
        raise too_many_attempts(attempt.cooldown)  # the last slot's lock is being written
    lock = await attempt.store.peek(attempt.lock_key, attempt.lock_spec)
    if not lock.allowed:  # locked while this attempt was counting
        raise too_many_attempts(lock.retry_after)
    return Admission((), counted.count)


async def record_failure(
    session: AsyncSession, attempt: LoginAttempt, admission: Admission
) -> HTTPException | None:
    """Settle a wrong password: the 429 to raise if it was the last slot, else ``None``.

    The failure itself was counted by :func:`admit`. Locking commits *session*:
    the caller answers by raising, and the request's unit of work rolls back on
    that path.
    """
    if admission.count < attempt.threshold:
        return None
    if admission.user_ids:
        for user_id in admission.user_ids:
            # Through the ORM, not an UPDATE, so the audit log records the lock.
            # Only ``locked_until`` and the count are written, so a concurrent
            # counting UPDATE cannot undo it — and none can run: this row has
            # no free slot until the lock lifts.
            user = await session.get(User, user_id, populate_existing=True)
            if user is not None:
                user.locked_until = attempt.now + timedelta(seconds=attempt.cooldown)
                user.failed_login_count = 0
        await session.commit()
    else:
        await attempt.store.hit(attempt.lock_key, attempt.lock_spec)
        await attempt.store.reset(attempt.account_key)
    return too_many_attempts(attempt.cooldown)


async def record_success(session: AsyncSession, attempt: LoginAttempt, admission: Admission):
    """Give the slots back after a correct password. Rides the request's own commit.

    Clears the count, never ``locked_until``: an attempt admitted before a lock
    landed must not lift it by succeeding afterwards.
    """
    await attempt.store.reset(attempt.ip_key)
    if admission.user_ids:
        await session.execute(
            update(User)
            .where(User.id.in_(admission.user_ids))
            .values(failed_login_count=0, last_failed_login_at=None, updated_at=User.updated_at)
            .execution_options(synchronize_session=False)
        )


async def release(session: AsyncSession, attempt: LoginAttempt, admission: Admission) -> None:
    """Give back the account slot of an attempt that must not count.

    For a correct password refused for another reason (an unverified email):
    that answer is not a failure. Commits, since the caller raises next.
    """
    await attempt.store.reset(attempt.ip_key)
    if admission.user_ids:
        await session.execute(
            update(User)
            .where(User.id.in_(admission.user_ids), User.failed_login_count > 0)  # ty: ignore[invalid-argument-type]
            .values(failed_login_count=User.failed_login_count - 1, updated_at=User.updated_at)
            .execution_options(synchronize_session=False)
        )
        await session.commit()
