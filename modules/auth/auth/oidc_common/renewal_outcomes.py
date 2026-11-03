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
from sqlalchemy import delete
from sqlmodel import col

from auth.constants import SESSION_ID_KEY
from auth.contracts.schemas import UserContext
from auth.models import RefreshOutcome
from auth.oidc_common.session import SessionKeys

logger = logging.getLogger(__name__)
_OUTCOME_TTL = 30
_LEASE_TTL = 15  # Above the token endpoint's 10-second timeout.
_WAIT_SECONDS = 3
_WORK_SECONDS = 12
_RETRY_SECONDS = 30


def _authority_keys(keys: SessionKeys) -> tuple[str, ...]:
    return tuple(
        k
        for k in (
            keys.user,
            keys.refresh,
            keys.retry,
            keys.identity,
            SESSION_ID_KEY,
            SESSION_EXPIRES_AT_KEY,
            *keys.obsolete,
        )
        if k is not None
    )


async def _load(app: Any, name: str) -> dict | None:
    async with independent_session(app) as db:
        row = await db.get(RefreshOutcome, name)
        result = row.session if row is not None and row.expires_at > time.time() else None
        await db.execute(
            delete(RefreshOutcome).where(
                col(RefreshOutcome.expires_at) <= int(time.time()),
            )
        )
        return result


async def _publish(app: Any, name: str, session: dict) -> None:
    async with independent_session(app) as db:
        await db.merge(
            RefreshOutcome(
                session_id=name,
                expires_at=int(time.time()) + _OUTCOME_TTL,
                session=session,
            )
        )


async def coordinated_refresh(request, keys: SessionKeys, sealed: str, renew) -> UserContext | None:
    session = request.session
    # Old cookies have no random id yet; identical ciphertext coordinates their
    # first renewal without storing or hashing the plaintext refresh credential.
    spent = hashlib.sha256(sealed.encode()).hexdigest()
    identity = session.get(SESSION_ID_KEY) or spent
    # The lock is per session, so renewals serialise. The outcome is bound to
    # the exact credential being spent: only requests carrying the same
    # pre-rotation cookie may adopt it, never an older copy of the cookie.
    lock = hashlib.sha256(f"{keys.refresh}:{identity}".encode()).hexdigest()
    name = hashlib.sha256(f"{keys.refresh}:{identity}:{spent}".encode()).hexdigest()
    held = lease(f"auth-refresh:{lock}", ttl=_LEASE_TTL, wait=_WAIT_SECONDS)
    waited = False
    try:
        if not await held.acquire(blocking=False):
            waited = True
            if not await held.acquire():
                session[keys.retry] = int(time.time()) + _RETRY_SECONDS
                return None
        try:
            async with asyncio.timeout(_WORK_SECONDS):
                outcome = await _load(request.app, name)
                if outcome is not None:
                    for key in _authority_keys(keys):
                        session.pop(key, None)
                    session.update(outcome)
                    if session.get(SESSION_EXPIRES_AT_KEY, 0) > time.time():
                        return UserContext.from_session_dict(session.get(keys.user))
                    return None
                if waited:
                    session[keys.retry] = int(time.time()) + _RETRY_SECONDS
                    return None
                session.setdefault(SESSION_ID_KEY, secrets.token_urlsafe(24))
                result = await renew()
                await _publish(
                    request.app,
                    name,
                    {key: session[key] for key in _authority_keys(keys) if key in session},
                )
                return result
        finally:
            await held.release()
    except Exception:
        # Storage/lease failures cannot prove a grant safe. Keep the cookie and
        # never expose SQL parameters (which include sealed credentials).
        logger.warning("OIDC refresh coordination unavailable")
        session[keys.retry] = int(time.time()) + _RETRY_SECONDS
        return None
