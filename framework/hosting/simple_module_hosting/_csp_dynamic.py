"""Per-response evaluation of module CSP providers (#434).

``register_csp_sources`` runs before DB settings hydrate, so origins that come
from a setting are declared as providers (``registry.add_provider(fn)``) and
evaluated here on each response. The finished policy is cached by the *value*
the providers return, so a settings edit changes the key on the next response
without any invalidation wiring.

Fail closed: a provider that raises, or a pair that fails the same validation
``CspSourceRegistry.add`` applies, contributes nothing — the static policy
still ships. Each distinct failure is logged once per process.
"""

from __future__ import annotations

import logging
from typing import Any

from simple_module_core.csp import CspSourceRegistry, is_valid_source

logger = logging.getLogger(__name__)

_CACHE_MAX = 32
_LOGGED_MAX = 256


class DynamicCsp:
    """Builds the CSP for one response from a static base plus provider output."""

    def __init__(self, base: str, registry: CspSourceRegistry) -> None:
        self.base = base
        self._registry = registry
        self._providers = registry.providers
        self._cache: dict[frozenset[tuple[str, str]], str] = {}
        self._logged: set[str] = set()

    def policy_for(self, app: Any) -> str:
        pairs = frozenset(self._collect(app))
        if not pairs:
            return self.base
        policy = self._cache.get(pairs)
        if policy is None:
            if len(self._cache) >= _CACHE_MAX:
                self._cache.clear()
            # Sorted so the clause order is stable for a given set of pairs.
            try:
                policy = self._registry.extend_policy(self.base, extra=sorted(pairs))
            except Exception as exc:
                # Last line of the fail-closed guarantee: this runs inside the
                # response for every page, so a bug here must cost the extra
                # origins, never the response.
                self._warn_once(
                    f"build:{type(exc).__name__}:{exc}",
                    "CSP provider policy build failed (%r); serving the static policy",
                    exc,
                )
                return self.base
            self._cache[pairs] = policy
        return policy

    def _collect(self, app: Any) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for provider in self._providers:
            name = getattr(provider, "__qualname__", repr(provider))
            try:
                pairs = list(provider(app))
            except Exception as exc:
                self._warn_once(
                    f"{name}:{type(exc).__name__}:{exc}",
                    "CSP provider %s raised %r; its sources are skipped",
                    name,
                    exc,
                )
                continue
            for pair in pairs:
                if (
                    isinstance(pair, tuple)
                    and len(pair) == 2
                    and isinstance(pair[0], str)
                    and isinstance(pair[1], str)
                    and is_valid_source(pair[0], pair[1])
                ):
                    out.append((pair[0], pair[1].strip()))
                else:
                    self._warn_once(
                        f"{name}:{pair!r}",
                        "CSP provider %s returned invalid pair %r; dropped",
                        name,
                        pair,
                    )
        return out

    def _warn_once(self, key: str, msg: str, *args: object) -> None:
        if key in self._logged:
            return
        if len(self._logged) >= _LOGGED_MAX:
            self._logged.clear()
        self._logged.add(key)
        logger.warning(msg, *args)
