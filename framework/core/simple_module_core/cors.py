"""CORS policy registry: modules declare which origins may call which paths.

The host registers a policy for ``/api/`` from its ``cors_*`` settings; a module
with a public, cross-origin surface (e.g. publicly served files) adds its own
through :meth:`~simple_module_core.module.ModuleBase.register_cors_policies`::

    def register_cors_policies(self, registry):
        registry.add_prefix(
            "/files/public/",
            CorsPolicy(origins=("*",), allow_credentials=False, methods=("GET", "HEAD")),
            enabled=lambda: app_settings.public_files_cors,
        )

The most specific match wins (exact, then regex, then longest prefix); a tie
keeps the first registration and logs a warning. ``enabled`` is evaluated per
request, so a DB-backed toggle needs no restart.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from simple_module_core.path_rules import KIND_EXACT, KIND_PREFIX, KIND_REGEX, PathRuleSet

__all__ = ["CorsPolicy", "CorsPolicyRegistry"]

WILDCARD = "*"


@dataclass(frozen=True, slots=True)
class CorsPolicy:
    origins: tuple[str, ...]
    allow_credentials: bool = False
    methods: tuple[str, ...] = ("GET",)
    headers: tuple[str, ...] = ()
    expose_headers: tuple[str, ...] = ()
    max_age: int = 600

    def __post_init__(self) -> None:
        if self.allow_credentials and WILDCARD in self.origins:
            raise ValueError("A CORS policy cannot combine origin '*' with credentials")
        if self.max_age < 0:
            raise ValueError("max_age must be >= 0")


class CorsPolicyRegistry:
    def __init__(self) -> None:
        self._rules: PathRuleSet[CorsPolicy] = PathRuleSet("CORS policy")

    def add_exact(
        self, path: str, policy: CorsPolicy, *, enabled: Callable[[], bool] | None = None
    ) -> None:
        self._rules.add(KIND_EXACT, path, policy, enabled=enabled)

    def add_prefix(
        self, prefix: str, policy: CorsPolicy, *, enabled: Callable[[], bool] | None = None
    ) -> None:
        self._rules.add(KIND_PREFIX, prefix, policy, enabled=enabled)

    def add_regex(
        self, pattern: str, policy: CorsPolicy, *, enabled: Callable[[], bool] | None = None
    ) -> None:
        self._rules.add(KIND_REGEX, pattern, policy, enabled=enabled)

    def match(self, method: str, path: str) -> CorsPolicy | None:
        """The governing policy for this request, or ``None`` (no CORS headers)."""
        return self._rules.match(method, path)

    def __len__(self) -> int:
        return len(self._rules)
