"""The principal resolver: ``Authorization: Bearer smpat_…`` / ``smsk_…`` → principal.

Appended to ``app.state.auth.principal_resolvers`` at startup. The ``users``
and ``keycloak`` providers return ``None`` for these prefixes, which is what
hands the request to this resolver.

Per request: a regex check, one indexed lookup by hash (no cache, so a revoke
is effective on the very next request), and for a personal token one read of
the owner with their roles through the app's user directory. Everything that
is not a usable token — unknown, revoked, expired, an inactive or disabled
owner, an owner whose roles the directory cannot read — is ``None``, which the
middleware turns into a 401.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from auth.contracts.schemas import UserContext
from auth.contracts.tokens import AUTH_KIND_PAT, AUTH_KIND_SERVICE, is_api_token, parse_bearer
from simple_module_core.tenancy import is_tenant_role
from simple_module_core.user_directory import UserDirectory, get_user_directory
from simple_module_db import ALL_TENANTS_OPTION, independent_session
from sqlalchemy import or_, select, update
from starlette.requests import Request

from api_tokens.constants import (
    FORBIDDEN_SERVICE_ROLES,
    LAST_USED_WRITE_INTERVAL_SECONDS,
    PERM_USE,
    TokenKind,
)
from api_tokens.models import ApiToken
from api_tokens.owner import usable_owner
from api_tokens.tokens import hash_token, is_well_formed

logger = logging.getLogger(__name__)

SERVICE_PRINCIPAL_PREFIX = "svc:"
"""Service principals are ``svc:<token id>``: not a user UUID, so they hold no
direct grants and can never be mistaken for an account."""


def _bearer(request: Request) -> str | None:
    credential = parse_bearer(request.headers.get("authorization"))
    if credential is None or not is_api_token(credential) or not is_well_formed(credential):
        return None
    return credential


def _usable(token: ApiToken, now: datetime) -> bool:
    return token.revoked_at is None and token.expires_at > now


async def _personal(db: Any, directory: UserDirectory, token: ApiToken) -> UserContext | None:
    if token.owner_user_id is None:
        return None
    owner_id = str(token.owner_user_id)
    user = await usable_owner(directory, db, owner_id)
    if user is None:
        return None
    principal = UserContext(
        id=owner_id,
        email=user.email,
        name=user.label,
        roles=list(user.roles or ()),
        auth_kind=AUTH_KIND_PAT,
        scopes=list(token.scopes),
    )
    # Pinned to the tenant it was created in, like a service key: the tenant
    # resolver acts for this tenant only (and only while the owner is still an
    # active member of it), never one named by a header, subdomain or session.
    principal.tenant_id = token.tenant_id
    # A personal token lives only as long as its owner may hold tokens: losing
    # ``api_tokens.use`` (which also takes away listing and revoking them)
    # retires every token they own, checked against their live, tenant-aware
    # permissions on each request (``lacks_required_permission``).
    principal.required_permission = PERM_USE
    return principal


def _service(token: ApiToken) -> UserContext:
    return UserContext(
        id=f"{SERVICE_PRINCIPAL_PREFIX}{token.id}",
        email="",
        name=token.name,
        # Refused at creation; dropped here too so a hand-edited row cannot
        # turn a service key into an admin — or a tenant owner: ``tenant:*``
        # roles come only from a membership, which a service key never has.
        roles=[
            r for r in token.roles if r not in FORBIDDEN_SERVICE_ROLES and not is_tenant_role(r)
        ],
        tenant_id=token.tenant_id,
        auth_kind=AUTH_KIND_SERVICE,
        scopes=list(token.scopes),
    )


async def touch_last_used(app: Any, token: ApiToken, now: datetime) -> None:
    """Record use at most once per interval, in its own short transaction.

    The ``WHERE`` repeats the staleness test, so concurrent requests on one
    token race to a single write rather than one each. ``updated_at`` is set
    to itself: it would otherwise be bumped by its ``onupdate`` and stop
    meaning "last edited". A failure here never fails the request.
    """
    cutoff = now - timedelta(seconds=LAST_USED_WRITE_INTERVAL_SECONDS)
    if token.last_used_at is not None and token.last_used_at > cutoff:
        return
    stmt = (
        update(ApiToken)
        .where(
            ApiToken.id == token.id,  # ty: ignore[invalid-argument-type]
            or_(ApiToken.last_used_at.is_(None), ApiToken.last_used_at <= cutoff),
        )
        .values(last_used_at=now, updated_at=ApiToken.updated_at)
        .execution_options(**{ALL_TENANTS_OPTION: True})
    )
    try:
        async with independent_session(app) as db:
            await db.execute(stmt)
    except Exception:
        logger.warning("api_tokens: could not record last use of %s", token.id, exc_info=True)


async def resolve_api_token(request: Request) -> UserContext | None:
    """``PrincipalResolver`` for ``api_tokens`` credentials. Never raises."""
    credential = _bearer(request)
    if credential is None:
        return None
    now = datetime.now(UTC)
    app = request.app
    try:
        async with app.state.sm.db.session_factory() as db:
            stmt = (
                select(ApiToken)
                .where(ApiToken.token_hash == hash_token(credential))  # ty: ignore[invalid-argument-type]
                .execution_options(**{ALL_TENANTS_OPTION: True})
            )
            token = (await db.execute(stmt)).scalar_one_or_none()
            if token is None or not _usable(token, now):
                return None
            if token.kind == TokenKind.PERSONAL:
                principal = await _personal(db, get_user_directory(app), token)
            elif token.kind == TokenKind.SERVICE:
                principal = _service(token)
            else:
                principal = None
    except Exception:
        logger.exception("api_tokens: token lookup failed; treating as unauthenticated")
        return None
    if principal is not None:
        await touch_last_used(app, token, now)
    return principal


__all__ = ["SERVICE_PRINCIPAL_PREFIX", "resolve_api_token", "touch_last_used"]
