"""Coordinate rotating grants and publish sealed cookie updates across workers."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time
from typing import Any

from simple_module_core.leases import lease
from simple_module_db import independent_session
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY
from sqlalchemy import delete, or_
from sqlmodel import col

from auth.constants import REFRESH_RETRY_AFTER_SECONDS, SESSION_AUTHORITY_KEY, SESSION_ID_KEY
from auth.contracts.schemas import UserContext
from auth.models import RefreshOutcome
from auth.oidc_common.session import SessionKeys

logger = logging.getLogger(__name__)
_OUTCOME_TTL = 30
_LEASE_TTL = 15  # Above the token endpoint's 10-second timeout.
_WAIT_SECONDS = 3
_WORK_SECONDS = 12
_PUBLISH_SECONDS = 2  # Work + publish stay inside the lease TTL.


def _authority_keys(keys: SessionKeys) -> tuple[str, ...]:
    return tuple(
        k
        for k in (
            keys.user,
            keys.refresh,
            keys.retry,
            keys.identity,
            SESSION_ID_KEY,
            SESSION_AUTHORITY_KEY,
            SESSION_EXPIRES_AT_KEY,
            *keys.obsolete,
        )
        if k is not None
    )


async def _load(app: Any, name: str) -> dict | None:
    async with independent_session(app) as db:
        row = await db.get(RefreshOutcome, name)
        return row.session if row is not None and row.expires_at > time.time() else None


def _lock_key(keys: SessionKeys, identity: str) -> str:
    return hashlib.sha256(f"{keys.refresh}:{identity}".encode()).hexdigest()


def _outcome_key(keys: SessionKeys, session: Any, sealed: str) -> str:
    # Old cookies have no random id yet; identical ciphertext coordinates their
    # first renewal without storing or hashing the plaintext refresh credential.
    spent = hashlib.sha256(sealed.encode()).hexdigest()
    identity = session.get(SESSION_ID_KEY) or spent
    return hashlib.sha256(f"{keys.refresh}:{identity}:{spent}".encode()).hexdigest()


async def _publish(app: Any, name: str, lock_key: str, session: dict) -> None:
    async with independent_session(app) as db:
        # Purge here, on the write path, so a lookup never takes a write lock.
        await db.execute(
            delete(RefreshOutcome).where(
                col(RefreshOutcome.expires_at) <= int(time.time()),
            )
        )
        await db.merge(
            RefreshOutcome(
                outcome_key=name,
                lock_key=lock_key,
                expires_at=int(time.time()) + _OUTCOME_TTL,
                session=session,
            )
        )


async def forget_outcomes(app: Any, keys: SessionKeys, session: Any) -> None:
    """Drop the session's shared outcomes at logout (best effort, never raises).

    Without this a replayed pre-rotation cookie could adopt the renewed
    principal for up to the outcome TTL after the user signed out.
    """
    try:
        matches = []
        identity = session.get(SESSION_ID_KEY)
        if identity:
            matches.append(col(RefreshOutcome.lock_key) == _lock_key(keys, identity))
        sealed = session.get(keys.refresh)
        if sealed:
            # An outcome this very cookie could adopt, e.g. an id-less legacy
            # cookie whose renewal another request already published.
            matches.append(col(RefreshOutcome.outcome_key) == _outcome_key(keys, session, sealed))
        if not matches:
            return
        # Wait out a renewal still in flight for this cookie, so its outcome
        # cannot be published just after the delete. Delete regardless.
        lock = _lock_key(keys, identity or hashlib.sha256(sealed.encode()).hexdigest())
        held = lease(f"auth-refresh:{lock}", ttl=_LEASE_TTL, wait=_LEASE_TTL)
        acquired = await held.acquire()
        try:
            async with independent_session(app) as db:
                await db.execute(delete(RefreshOutcome).where(or_(*matches)))
        finally:
            if acquired:
                await held.release()
    except Exception as exc:
        logger.warning("OIDC refresh outcome not cleared (%s)", type(exc).__name__)


async def coordinated_refresh(request, keys: SessionKeys, sealed: str, renew) -> UserContext | None:
    session = request.session
    identity = session.get(SESSION_ID_KEY) or hashlib.sha256(sealed.encode()).hexdigest()
    # The lock is per session, so renewals serialise. The outcome is bound to
    # the exact credential being spent: only requests carrying the same
    # pre-rotation cookie may adopt it, never an older copy of the cookie.
    lock = _lock_key(keys, identity)
    name = _outcome_key(keys, session, sealed)
    held = lease(f"auth-refresh:{lock}", ttl=_LEASE_TTL, wait=_WAIT_SECONDS)
    waited = False
    try:
        if not await held.acquire(blocking=False):
            waited = True
            if not await held.acquire():
                # Leave the cookie untouched: a waiter's Set-Cookie would carry
                # the already-spent refresh token and could land after the
                # winner's. This request alone goes unauthenticated.
                return None
        try:
            async with asyncio.timeout(_WORK_SECONDS):
                outcome = await _load(request.app, name)
                if outcome is not None:
                    # Unmarked outcomes come from pre-#750 processes during a rolling
                    # upgrade; they are bound to this session's own spent credential.
                    marker = outcome.get(SESSION_AUTHORITY_KEY)
                    if marker is not None and marker != session.get(SESSION_AUTHORITY_KEY):
                        session.clear()
                        return None
                    for key in _authority_keys(keys):
                        session.pop(key, None)
                    session.update(outcome)
                    if session.get(SESSION_EXPIRES_AT_KEY, 0) > time.time():
                        return UserContext.from_session_dict(session.get(keys.user))
                    return None
                if waited:
                    return None  # the winner failed or its outcome expired; see above
                session.setdefault(SESSION_ID_KEY, secrets.token_urlsafe(24))
                result = await renew()
            # Publishing has its own timeout: renew() already stored the rotated
            # token, so a slow publish must not look like a failed renewal, and
            # it must end before the lease expires and admits a second grant.
            try:
                # Filed under the id the renewed cookie carries, so its logout
                # finds the row even when a legacy cookie had no id before. A
                # rejected grant cleared the session, so it keeps the lock key.
                async with asyncio.timeout(_PUBLISH_SECONDS):
                    await _publish(
                        request.app,
                        name,
                        _lock_key(keys, session.get(SESSION_ID_KEY) or identity),
                        {key: session[key] for key in _authority_keys(keys) if key in session},
                    )
            except Exception as exc:
                # The grant already succeeded and the cookie holds the rotated
                # token: losing the shared outcome only costs waiters a retry.
                logger.warning("OIDC refresh outcome not shared (%s)", type(exc).__name__)
            return result
        finally:
            await held.release()
    except Exception as exc:
        # Storage/lease failures cannot prove a grant safe. Keep the cookie and
        # never log the exception text (SQL parameters include sealed credentials).
        logger.warning("OIDC refresh coordination unavailable (%s)", type(exc).__name__)
        session[keys.retry] = int(time.time()) + REFRESH_RETRY_AFTER_SECONDS
        return None
