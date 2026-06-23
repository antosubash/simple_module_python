"""Public-route registry — modules declare routes the auth layer must NOT gate.

``AuthMiddleware`` gates every request behind the active auth provider. Modules
that expose anonymous read APIs (STAC / OGC API / TileJSON, public webhooks,
status pages) contribute exemptions here via
:meth:`~simple_module_core.module.ModuleBase.register_public_routes`. The host
collects them into one registry at boot and the middleware consults it on every
request.

Unlike the legacy ``AuthProvider.get_public_paths`` contract — a flat tuple of
prefixes matched with ``str.startswith`` — a :class:`PublicRoute` is
**method-aware** and supports prefix / exact / suffix / regex matching. That
lets a module expose ``GET /api/gis/datasets/{id}/tilejson`` while leaving
``PATCH``/``POST`` siblings under the same prefix authenticated.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_MatchKind = str  # one of: "prefix" | "exact" | "suffix" | "regex"
_VALID_KINDS = ("prefix", "exact", "suffix", "regex")


class PublicRoute:
    """A single anonymous-access rule.

    Args:
        pattern: The path (or path fragment / regex) to match against
            ``request.url.path``.
        methods: HTTP methods this rule applies to (case-insensitive). ``None``
            (the default) means *any* method — the rule matches every verb.
        kind: How ``pattern`` is interpreted — ``"prefix"`` (default, matches
            any path that starts with it), ``"exact"``, ``"suffix"``, or
            ``"regex"`` (anchored at the start of the path via ``re.match``).
    """

    __slots__ = ("_regex", "kind", "methods", "pattern")

    def __init__(
        self,
        pattern: str,
        *,
        methods: Iterable[str] | None = None,
        kind: _MatchKind = "prefix",
    ) -> None:
        if kind not in _VALID_KINDS:
            raise ValueError(f"Unknown match kind {kind!r}; expected one of {_VALID_KINDS}")
        self.pattern = pattern
        self.methods: frozenset[str] | None = (
            None if methods is None else frozenset(m.upper() for m in methods)
        )
        self.kind = kind
        self._regex = re.compile(pattern) if kind == "regex" else None

    def matches(self, method: str, path: str) -> bool:
        """Return ``True`` if *method* + *path* are exempt under this rule."""
        if self.methods is not None and method.upper() not in self.methods:
            return False
        if self.kind == "prefix":
            return path.startswith(self.pattern)
        if self.kind == "exact":
            return path == self.pattern
        if self.kind == "suffix":
            return path.endswith(self.pattern)
        assert self._regex is not None  # kind == "regex"
        return self._regex.match(path) is not None

    def __repr__(self) -> str:
        methods = "*" if self.methods is None else ",".join(sorted(self.methods))
        return f"PublicRoute({self.pattern!r}, kind={self.kind!r}, methods={methods})"


class PublicRouteRegistry:
    """Aggregates every module's :class:`PublicRoute` rules.

    Populated once during boot (``register_public_routes`` hook) and read on
    every unauthenticated request by ``AuthMiddleware`` — effectively immutable
    after the registration phase.
    """

    def __init__(self) -> None:
        self._routes: list[PublicRoute] = []

    def add(
        self,
        route: PublicRoute | str,
        *,
        methods: Iterable[str] | None = None,
        kind: _MatchKind = "prefix",
    ) -> None:
        """Register a rule — either a prebuilt :class:`PublicRoute` or a pattern.

        Passing a string builds a :class:`PublicRoute` from ``methods``/``kind``;
        passing a :class:`PublicRoute` ignores those keyword arguments.
        """
        if isinstance(route, PublicRoute):
            self._routes.append(route)
        else:
            self._routes.append(PublicRoute(route, methods=methods, kind=kind))

    def add_prefix(self, prefix: str, *, methods: Iterable[str] | None = None) -> None:
        """Exempt any path starting with *prefix*."""
        self._routes.append(PublicRoute(prefix, methods=methods, kind="prefix"))

    def add_exact(self, path: str, *, methods: Iterable[str] | None = None) -> None:
        """Exempt exactly *path*."""
        self._routes.append(PublicRoute(path, methods=methods, kind="exact"))

    def add_suffix(self, suffix: str, *, methods: Iterable[str] | None = None) -> None:
        """Exempt any path ending with *suffix*."""
        self._routes.append(PublicRoute(suffix, methods=methods, kind="suffix"))

    def add_regex(self, pattern: str, *, methods: Iterable[str] | None = None) -> None:
        """Exempt any path whose start matches *pattern* (``re.match`` semantics)."""
        self._routes.append(PublicRoute(pattern, methods=methods, kind="regex"))

    def matches(self, method: str, path: str) -> bool:
        """Return ``True`` if any registered rule exempts *method* + *path*."""
        return any(route.matches(method, path) for route in self._routes)

    @property
    def routes(self) -> list[PublicRoute]:
        """All registered rules (a copy — mutating it doesn't affect the registry)."""
        return list(self._routes)


__all__ = ["PublicRoute", "PublicRouteRegistry"]
