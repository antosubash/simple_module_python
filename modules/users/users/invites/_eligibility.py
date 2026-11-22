"""Shared invite account eligibility checks."""

from __future__ import annotations

from typing import Any


def is_invite_eligible(user: Any) -> bool:
    """True when *user* is active, enabled, and uses local password auth."""
    return bool(user.is_active and user.disabled_at is None and not user.is_external)
