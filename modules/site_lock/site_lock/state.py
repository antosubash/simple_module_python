"""Module-owned state attached to ``app.state.site_lock``."""

from __future__ import annotations

from dataclasses import dataclass, field

from site_lock import constants as c
from site_lock.rate_limit import AttemptLimiter
from site_lock.settings import SiteLockSettings


def _default_limiter() -> AttemptLimiter:
    return AttemptLimiter(
        max_failures=c.MAX_FAILURES,
        window_seconds=c.WINDOW_SECONDS,
        cooldown_seconds=c.COOLDOWN_SECONDS,
    )


@dataclass
class SiteLockState:
    """Per-app site-lock state.

    ``settings`` is reassigned in place by ``settings.reload`` on a hot
    reload, so this dataclass must stay mutable. ``limiter`` survives those
    reloads, which is what keeps an in-flight brute-force cooldown from being
    cleared by an unrelated settings save.
    """

    settings: SiteLockSettings
    limiter: AttemptLimiter = field(default_factory=_default_limiter)


__all__ = ["SiteLockState"]
