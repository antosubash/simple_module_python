"""Request credential context for audit attribution.

Set by the auth middleware next to ``current_user_id`` and reset with it: how
the request authenticated (``session``, ``pat``, ``service``, ...) and, for a
token, its credential id. Audit rows record both.
"""

from __future__ import annotations

from contextvars import ContextVar

current_auth_kind: ContextVar[str | None] = ContextVar("current_auth_kind", default=None)
current_token_id: ContextVar[str | None] = ContextVar("current_token_id", default=None)

__all__ = ["current_auth_kind", "current_token_id"]
