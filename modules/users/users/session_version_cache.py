"""In-process cache of ``User.session_version``, the revocation counter.

Split out of :mod:`users.provider` so that file keeps one job — resolving a
request to a principal — while the caching trade-off (a bounded window in
which one worker has not yet seen another worker's revocation) is stated in
one place and testable on its own. Re-exported from ``users.provider``, which
is where callers reach for it.
"""

from __future__ import annotations

from cachetools import TTLCache

__all__ = [
    "SESSION_VERSION_TTL_SECONDS",
    "clear_session_version_cache",
    "forget_session_version",
    "peek_session_version",
    "read_session_version",
    "store_session_version",
]

SESSION_VERSION_TTL_SECONDS = 30
"""How long a read of ``User.session_version`` is reused without re-reading.

``_version_still_current`` runs on the cached-context path, which is most
requests, so the check was one indexed primary-key read per page load. The
cost of the cache is a bounded staleness window: a revocation performed in
*another* worker process takes up to this long to be seen here. The process
that performed it calls :func:`forget_session_version` and sees it at once, so
the browser that pressed "Sign out everywhere" is never told it worked while
still being let in.

30 seconds is chosen to be shorter than any plausible "did it work?" retry and
long enough to collapse a page's worth of requests into one read.
"""

_SESSION_VERSIONS: TTLCache = TTLCache(maxsize=10_000, ttl=SESSION_VERSION_TTL_SECONDS)
"""``user_id -> session_version`` (or ``None`` for "no such row").

Bounded and per-process. An LRU eviction is not a correctness problem: a miss
just costs the read the cache was avoiding.
"""


def forget_session_version(user_id) -> None:
    """Drop this account's cached revocation counter.

    Called by whatever just changed it — "sign out everywhere" and a password
    change — so this process stops answering from the value it read before.
    """
    _SESSION_VERSIONS.pop(user_id, None)


def peek_session_version(user_id):
    """The cached counter without reading the DB, or ``None`` when not cached.

    For tests and diagnostics: the cache stores ``None`` for a missing row, so
    a caller that needs to tell "absent" from "cached as missing" apart should
    use ``user_id in _SESSION_VERSIONS``.
    """
    return _SESSION_VERSIONS.get(user_id)


def clear_session_version_cache() -> None:
    """Empty the cache — used by tests that need a cold read."""
    _SESSION_VERSIONS.clear()


def read_session_version(user_id) -> tuple[bool, int | None]:
    """``(hit, stored)`` — ``hit`` is False when nothing is cached.

    Two return values rather than a sentinel because ``None`` is a legitimate
    cached answer ("no such row"), and collapsing it with "not cached" would
    turn a deleted account into a DB read on every request.
    """
    if user_id in _SESSION_VERSIONS:
        return True, _SESSION_VERSIONS[user_id]
    return False, None


def store_session_version(user_id, stored: int | None) -> None:
    """Record what the DB answered for this account."""
    _SESSION_VERSIONS[user_id] = None if stored is None else int(stored)
