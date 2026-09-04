"""What a user row *is*, in one word — shared by the DTO and the filters.

Both the status pill and the Status dropdown answer the same question, so the
rule lives once: a Python function for a row already in hand, and the SQL
predicate that selects the same set. Two copies of "invited means unverified
with an ``invited_at``" would drift the first time one of them changed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from users.models import User


def user_state(is_active: bool, is_verified: bool, invited_at: datetime | None) -> str:
    """One of :data:`users.contracts.schemas.USER_STATES`.

    Order matters: a disabled account is disabled whatever else is true of it,
    and an unverified one splits on whether somebody invited it or it walked in
    through public signup.
    """
    if not is_active:
        return "disabled"
    if is_verified:
        return "active"
    return "invited" if invited_at is not None else "unverified"


def _active() -> Any:
    return (User.is_active.is_(True)) & (User.is_verified.is_(True))


def _unverified() -> Any:
    return (User.is_active.is_(True)) & (User.is_verified.is_(False)) & (User.invited_at.is_(None))


def _invited() -> Any:
    return (
        (User.is_active.is_(True)) & (User.is_verified.is_(False)) & (User.invited_at.isnot(None))
    )


def _disabled() -> Any:
    return User.is_active.is_(False)


STATUS_CONDITIONS: dict[str, Callable[[], Any]] = {
    "active": _active,
    "unverified": _unverified,
    "invited": _invited,
    "disabled": _disabled,
}
"""The SQL half of :func:`user_state`, keyed by the same words.

Callables rather than expressions so the column references are built when the
filter is applied, not at import time."""
