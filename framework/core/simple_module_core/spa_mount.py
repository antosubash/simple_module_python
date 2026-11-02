"""Legacy SPA mounts: a built client-routed app served under a URL prefix.

Porting a large app step by step means running its existing SPA next to new
Inertia pages. A module declares the SPA through
:meth:`~simple_module_core.module.ModuleBase.spa_mounts`; the host serves its
build output with an ``index.html`` fallback for deep links and tells the
Inertia client to leave links into the prefix alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SPA_AUTH_REQUIRED = "required"
SPA_AUTH_PUBLIC = "public"
_AUTH_MODES = frozenset({SPA_AUTH_REQUIRED, SPA_AUTH_PUBLIC})

# Paths the framework or host owns outright; a mount here would shadow them.
RESERVED_PREFIXES = ("/api", "/admin", "/setup", "/i18n", "/health", "/static", "/modules")


def normalise_prefix(prefix: str) -> str:
    """``"/legacy/"`` -> ``"/legacy"``; the root and relative paths are refused."""
    cleaned = prefix.strip().rstrip("/")
    if not cleaned.startswith("/") or ".." in cleaned.split("/") or " " in cleaned:
        raise ValueError(f"SPA mount prefix {prefix!r} must be an absolute URL path like '/legacy'")
    return cleaned


@dataclass(frozen=True)
class SpaMount:
    """One legacy SPA: ``dist_dir`` served at ``prefix`` with deep-link fallback.

    ``auth="required"`` leaves the mount behind ``AuthMiddleware`` (anonymous
    visitors are sent to login); ``"public"`` exempts GET/HEAD from it.
    """

    prefix: str
    dist_dir: Path
    index: str = "index.html"
    auth: str = SPA_AUTH_REQUIRED

    def __post_init__(self) -> None:
        object.__setattr__(self, "prefix", normalise_prefix(self.prefix))
        object.__setattr__(self, "dist_dir", Path(self.dist_dir))
        if self.auth not in _AUTH_MODES:
            raise ValueError(
                f"SpaMount.auth must be one of {sorted(_AUTH_MODES)}, got {self.auth!r}"
            )
        if not self.index or "/" in self.index or ".." in self.index:
            raise ValueError(f"SpaMount.index must be a bare file name, got {self.index!r}")


def prefixes_overlap(a: str, b: str) -> bool:
    """Whether one path prefix contains the other, on whole segments."""
    a, b = a.rstrip("/"), b.rstrip("/")
    return bool(a) and bool(b) and (a == b or a.startswith(b + "/") or b.startswith(a + "/"))
