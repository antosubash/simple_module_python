"""Per-path request-body ceilings modules declare for the body-size guard.

The host ships one global ceiling (``HostSettings.max_request_body_bytes``).
A module whose endpoint legitimately takes more — a multipart upload — or
should take far less raises or lowers it for that route through
:meth:`~simple_module_core.module.ModuleBase.register_body_limits`::

    def register_body_limits(self, registry):
        registry.add_prefix("/api/file-storage/upload", 100 * 1024 * 1024)

``max_bytes`` may be a callable ``(app) -> int`` for a limit that is itself a
runtime setting; it is evaluated per request. The first matching rule in
registration order wins, and its value *replaces* the global ceiling.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from simple_module_core.public_routes import PublicRoute

__all__ = ["BodyLimitRegistry"]

MaxBytes = int | Callable[[Any], int]


class BodyLimitRegistry:
    def __init__(self) -> None:
        self._rules: list[tuple[PublicRoute, MaxBytes]] = []

    def add(
        self,
        pattern: str,
        max_bytes: MaxBytes,
        *,
        methods: Iterable[str] | None = None,
        kind: str = "prefix",
    ) -> None:
        """Register a ceiling. ``kind`` is prefix / exact / suffix / regex."""
        if isinstance(max_bytes, int) and max_bytes < 0:
            raise ValueError("max_bytes must be >= 0 (0 means unlimited)")
        self._rules.append((PublicRoute(pattern, methods=methods, kind=kind), max_bytes))

    def add_prefix(
        self, prefix: str, max_bytes: MaxBytes, *, methods: Iterable[str] | None = None
    ) -> None:
        self.add(prefix, max_bytes, methods=methods, kind="prefix")

    def add_exact(
        self, path: str, max_bytes: MaxBytes, *, methods: Iterable[str] | None = None
    ) -> None:
        self.add(path, max_bytes, methods=methods, kind="exact")

    def add_regex(
        self, pattern: str, max_bytes: MaxBytes, *, methods: Iterable[str] | None = None
    ) -> None:
        self.add(pattern, max_bytes, methods=methods, kind="regex")

    def limit_for(self, method: str, path: str, app: Any = None) -> int | None:
        """The override for this request, or ``None`` to use the global ceiling.

        ``0`` means "unlimited for this route".
        """
        for route, max_bytes in self._rules:
            if route.matches(method, path):
                return max_bytes if isinstance(max_bytes, int) else int(max_bytes(app))
        return None

    def __len__(self) -> int:
        return len(self._rules)
