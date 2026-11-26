"""Public helper to drop a request's principal mid-request."""

from __future__ import annotations

from simple_module_db.models.credential import current_auth_kind, current_token_id
from simple_module_db.models.listeners import current_user_id
from starlette.requests import HTTPConnection

__all__ = ["forget_principal"]


def forget_principal(request: HTTPConnection) -> None:
    """Drop the principal, its permissions and audit identity (tenant untouched)."""
    request.state.user = None
    request.state.resolved_permissions = set()
    current_user_id.set(None)
    current_auth_kind.set(None)
    current_token_id.set(None)
