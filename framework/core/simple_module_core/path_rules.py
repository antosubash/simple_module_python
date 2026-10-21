"""Most-specific-wins path matching shared by the CORS and rate-limit registries.

``BodyLimitRegistry`` takes the first matching rule; the registries built on this
helper instead pick the *most specific* one, so registration order between
modules (which follows dependency order, not intent) cannot let a broad prefix
shadow a narrow exact path. Specificity is exact > regex > longest prefix.

Standalone on purpose: ``public_routes`` imports ``rate_limit``, so this cannot
reuse :class:`~simple_module_core.public_routes.PublicRoute` without a cycle.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

__all__ = ["KIND_EXACT", "KIND_PREFIX", "KIND_REGEX", "PathRuleSet"]

logger = logging.getLogger(__name__)

KIND_EXACT = "exact"
KIND_REGEX = "regex"
KIND_PREFIX = "prefix"
_KINDS = (KIND_EXACT, KIND_REGEX, KIND_PREFIX)
# Higher beats lower; prefixes then compare by length.
_RANK = {KIND_PREFIX: 0, KIND_REGEX: 1, KIND_EXACT: 2}


@dataclass(slots=True)
class _Entry[T]:
    kind: str
    pattern: str
    value: T
    methods: frozenset[str] | None
    enabled: Callable[[], bool] | None
    regex: re.Pattern[str] | None = field(default=None)

    def matches(self, method: str, path: str) -> bool:
        if self.methods is not None and method.upper() not in self.methods:
            return False
        if self.kind == KIND_EXACT:
            return path == self.pattern
        if self.kind == KIND_PREFIX:
            return path.startswith(self.pattern)
        assert self.regex is not None
        return self.regex.match(path) is not None

    def specificity(self) -> tuple[int, int]:
        return (_RANK[self.kind], len(self.pattern) if self.kind == KIND_PREFIX else 0)


class PathRuleSet[T]:
    """An ordered set of ``(kind, pattern, methods) -> value`` rules."""

    def __init__(self, what: str = "rule") -> None:
        self._what = what
        self._entries: list[_Entry[T]] = []

    def add(
        self,
        kind: str,
        pattern: str,
        value: T,
        *,
        methods: Iterable[str] | None = None,
        enabled: Callable[[], bool] | None = None,
    ) -> None:
        if kind not in _KINDS:
            raise ValueError(f"Unknown match kind {kind!r}; expected one of {_KINDS}")
        method_set = None if methods is None else frozenset(m.upper() for m in methods)
        entry = _Entry(
            kind,
            pattern,
            value,
            method_set,
            enabled,
            re.compile(pattern) if kind == KIND_REGEX else None,
        )
        for other in self._entries:
            if other.kind == kind and other.pattern == pattern and _overlap(other, entry):
                logger.warning(
                    "Duplicate %s for %s %r; the first registered wins",
                    self._what,
                    kind,
                    pattern,
                )
                break
        self._entries.append(entry)

    def match(self, method: str, path: str) -> T | None:
        """The value of the most specific enabled rule for *method* + *path*."""
        found = self.match_entry(method, path)
        return None if found is None else found[2]

    def match_entry(self, method: str, path: str) -> tuple[str, str, T] | None:
        """Like :meth:`match` but ``(kind, pattern, value)``, to name what matched."""
        best: _Entry[T] | None = None
        for entry in self._entries:
            if not entry.matches(method, path):
                continue
            if entry.enabled is not None and not entry.enabled():
                continue
            # Strict ``>`` keeps the first registered on a tie.
            if best is None or entry.specificity() > best.specificity():
                best = entry
        return None if best is None else (best.kind, best.pattern, best.value)

    def __len__(self) -> int:
        return len(self._entries)


def _overlap(a: _Entry, b: _Entry) -> bool:
    return a.methods is None or b.methods is None or bool(a.methods & b.methods)
