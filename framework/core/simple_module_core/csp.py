"""Registry for module-contributed Content-Security-Policy sources.

Modules whose frontend loads assets from an external origin (a font CDN, a
tile server, an analytics endpoint) declare those origins through
``ModuleBase.register_csp_sources``. The host folds them into the CSP it
already ships — the module never rewrites the whole policy, and a typo'd
origin fails loudly at boot instead of silently weakening the header.
"""

from __future__ import annotations

import re

__all__ = ["CspSourceError", "CspSourceRegistry"]

# Fetch directives a module may extend. Deliberately excludes the policy's
# structural directives (default-src, base-uri, form-action, frame-ancestors,
# sandbox): widening those changes the security posture of the whole app and
# belongs to the host operator, not a module.
_EXTENDABLE_DIRECTIVES = frozenset(
    {
        "script-src",
        "script-src-elem",
        "style-src",
        "style-src-elem",
        "img-src",
        "font-src",
        "connect-src",
        "media-src",
        "frame-src",
        "worker-src",
        "child-src",
    }
)

# A source is a scheme, an origin (optionally with scheme/wildcard/port), or
# a data-ish scheme keyword. One token — anything that could smuggle a second
# token or terminate the clause (whitespace, ";", quotes) is rejected.
_SOURCE_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:(?://)?)?(?:\*\.)?[^\s;'\"*]*$")

# CSP3 fallback chains: when a directive is absent from a policy, the browser
# consults these directives in order (ending at ``default-src``). A clause we
# append for a previously-absent directive must be seeded from the nearest
# clause the policy already has along this chain — seeding with a bare
# ``'self'`` would *narrow* the policy (e.g. a fresh ``style-src-elem`` clause
# cuts off the fallback to ``style-src`` and silently drops its
# ``'unsafe-inline'`` and font origins).
_FALLBACK_CHAINS: dict[str, tuple[str, ...]] = {
    "script-src-elem": ("script-src", "default-src"),
    "style-src-elem": ("style-src", "default-src"),
    "frame-src": ("child-src", "default-src"),
    "worker-src": ("child-src", "script-src", "default-src"),
}


class CspSourceError(ValueError):
    """Invalid CSP directive or source declared by a module."""


class CspSourceRegistry:
    """Collects per-directive extra CSP sources from modules."""

    def __init__(self) -> None:
        self._sources: dict[str, list[str]] = {}

    def add(self, directive: str, source: str) -> None:
        """Allow ``source`` in ``directive``, e.g. ``add("style-src", "https://rsms.me")``."""
        if directive not in _EXTENDABLE_DIRECTIVES:
            raise CspSourceError(
                f"CSP directive {directive!r} is not extendable; "
                f"choose one of {sorted(_EXTENDABLE_DIRECTIVES)}"
            )
        token = source.strip()
        if not token or not _SOURCE_RE.match(token):
            raise CspSourceError(
                f"invalid CSP source {source!r} for {directive}: must be a single "
                "origin or scheme token (no spaces, quotes, wildcards-only, or ';')"
            )
        bucket = self._sources.setdefault(directive, [])
        if token not in bucket:
            bucket.append(token)

    def __bool__(self) -> bool:
        return bool(self._sources)

    @property
    def sources(self) -> dict[str, tuple[str, ...]]:
        return {directive: tuple(items) for directive, items in self._sources.items()}

    def extend_policy(self, policy: str) -> str:
        """Fold the registered sources into an existing policy string.

        Existing clauses keep their order and gain only sources they don't
        already list. A directive absent from the policy is appended as a new
        clause seeded from the clause the browser would otherwise have fallen
        back to (per ``_FALLBACK_CHAINS``, ending at ``default-src``) —
        without that seed the new clause would *narrow* the policy, since the
        browser stops consulting the fallback once the directive exists.
        """
        if not self._sources:
            return policy
        directives: dict[str, list[str]] = {}
        order: list[str] = []
        for clause in policy.split(";"):
            clause = clause.strip()
            if not clause:
                continue
            directive, _, rest = clause.partition(" ")
            directives[directive] = rest.split()
            order.append(directive)
        for directive, extras in self._sources.items():
            if directive not in directives:
                directives[directive] = list(self._seed_sources(directive, directives))
                order.append(directive)
            bucket = directives[directive]
            bucket.extend(e for e in extras if e not in bucket)
        return "; ".join(f"{d} {' '.join(directives[d])}".rstrip() for d in order)

    @staticmethod
    def _seed_sources(directive: str, directives: dict[str, list[str]]) -> list[str]:
        """Sources a brand-new clause inherits from its CSP fallback chain."""
        for fallback in (*_FALLBACK_CHAINS.get(directive, ()), "default-src"):
            if fallback in directives:
                return directives[fallback]
        return ["'self'"]
