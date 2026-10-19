"""The 403 raised when a principal lacks a named permission."""

from __future__ import annotations

from fastapi import HTTPException

__all__ = ["PERMISSION_DENIED_PREFIX", "PermissionDenied"]

PERMISSION_DENIED_PREFIX = "Permission required: "
"""How the default 403 message spells the missing permission (human text only).

Nothing parses it: handlers read :attr:`PermissionDenied.permission`.
"""


class PermissionDenied(HTTPException):
    """A 403 that knows which permission was missing.

    ``detail`` is a human message; the 403 error page and any other consumer
    read :attr:`permission` rather than parsing that text.
    """

    def __init__(self, permission: str, detail: str | None = None) -> None:
        super().__init__(
            status_code=403,
            detail=detail if detail is not None else f"{PERMISSION_DENIED_PREFIX}{permission}",
        )
        self.permission = permission
