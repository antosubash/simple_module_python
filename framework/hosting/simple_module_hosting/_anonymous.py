"""Demote a request's principal to the anonymous visitor, mid-request.

Used when a credential authenticated but must not act as its account here: an
API token on a public route (``token_guard``), or a token whose owner no
longer holds the permission it requires (``permissions``). "Anonymous" means
all of it — no user, no permissions, no audit identity, and the tenant an
anonymous request would have resolved to rather than the one the credential
pinned.
"""

from __future__ import annotations

from simple_module_db.listeners import current_user_id
from starlette.requests import HTTPConnection

from simple_module_hosting._tenant import reresolve_tenant


async def demote_to_anonymous(request: HTTPConnection) -> None:
    """Drop the principal and re-run tenant resolution as anonymous."""
    request.state.user = None
    request.state.resolved_permissions = set()
    current_user_id.set(None)
    await reresolve_tenant(request)


__all__ = ["demote_to_anonymous"]
