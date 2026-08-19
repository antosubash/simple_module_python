"""Env-only settings read before the database is available.

Everything here is needed either to connect to the DB, sign session cookies,
or configure the Python process (logging, Vite asset URLs, module allowlist).
These values stay in ``.env`` — all other settings live in the DB.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.discovery import DEFAULT_AUTH_PROVIDER
from simple_module_core.environments import NON_PROD_ENVIRONMENTS

_PLACEHOLDER_SECRET_KEY = "change-me-in-production"

# How many parent directories to probe for a `.env` above the cwd. One level
# covers the workspace layout (`host/` → root); a couple more cover running
# from `modules/<name>/`. Bounded so an unrelated `.env` far up the tree
# (e.g. in $HOME) is never picked up by accident.
_ENV_WALK_LIMIT = 4


def _discover_env_file() -> Path | str:
    """Locate the project ``.env`` regardless of which subdirectory runs us.

    ``SM_PROJECT_ROOT`` wins when set (the convention every out-of-process
    tool in this repo already follows — see ``simple_module_core.dotenv``).
    Otherwise walk up from the cwd: the web process chdirs to the workspace
    root so this finds ``./.env`` immediately, while a CLI invoked from
    ``host/`` or ``modules/<name>/`` finds the same file its app uses
    instead of silently loading nothing.
    """
    explicit = os.environ.get("SM_PROJECT_ROOT")
    if explicit:
        return Path(explicit) / ".env"
    current = Path.cwd()
    home = Path.home()
    for candidate in (current, *current.parents[:_ENV_WALK_LIMIT]):
        if candidate == home:
            break
        env = candidate / ".env"
        if env.is_file():
            return env
        # A `.git` marks the repository root: never ascend past it, or a
        # nested checkout (a git worktree, a repo inside another repo)
        # would silently load the *outer* project's `.env`.
        if (candidate / ".git").exists():
            break
    return ".env"


def _project_anchor(env_file: Path | str) -> Path:
    """Directory that relative sqlite paths are written against."""
    explicit = os.environ.get("SM_PROJECT_ROOT")
    if explicit:
        return Path(explicit)
    if isinstance(env_file, Path):
        return env_file.parent
    return Path.cwd()


def _absolutize_sqlite_url(url: str, *, anchor: Path) -> str:
    """Rewrite a relative sqlite path to an absolute one under ``anchor``.

    ``sqlite+aiosqlite:///./host/app.db`` means "relative to the project
    root" by convention, but SQLAlchemy resolves it against the process cwd
    — correct in the web process (which chdirs) and silently wrong in every
    CLI run from a subdirectory. Absolute paths (``:////...``), ``:memory:``,
    and non-sqlite URLs pass through untouched.
    """
    if not url.startswith("sqlite"):
        return url
    scheme, sep, rest = url.partition(":///")
    if not sep or not rest or rest.startswith("/") or rest.startswith(":memory:"):
        return url
    path_part, query_sep, query = rest.partition("?")
    resolved = (anchor / path_part).resolve()
    return f"{scheme}:///{resolved}{query_sep}{query}"


_ENV_FILE = _discover_env_file()


class BootstrapSettings(BaseSettings):
    """Pre-DB bootstrap environment knobs."""

    model_config = SettingsConfigDict(env_prefix="SM_", env_file=_ENV_FILE, extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./app.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True
    db_pool_recycle: int = 1800

    environment: str = "development"
    secret_key: str = _PLACEHOLDER_SECRET_KEY
    vite_dev_url: str = "http://localhost:5050"
    debug: bool = False

    # Trust the X-Forwarded-* headers from a fronting reverse proxy. Unset by
    # default (no proxy trusted). Set to ``*`` to trust any peer (correct when
    # the container is only reachable through a single proxy), or a comma-
    # separated list of proxy IPs / CIDRs. Drives uvicorn's
    # ProxyHeadersMiddleware so request.url.scheme reflects X-Forwarded-Proto
    # behind a TLS-terminating proxy — without it Inertia's pushState throws a
    # cross-scheme SecurityError and login breaks (GH #223).
    trusted_proxy: str | None = None

    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    modules_enabled: list[str] | None = None

    auth_provider: str = DEFAULT_AUTH_PROVIDER
    """Which auth provider module to activate (``SM_AUTH_PROVIDER``).

    ``users`` and ``keycloak`` both provide authentication and only one may be
    active at a time. When both are installed this picks the winner; the other
    is skipped at discovery. Ignored when only one is installed.
    """

    auth_public_paths: list[str] = []
    """Host-level anonymous-access path prefixes (``SM_AUTH_PUBLIC_PATHS``).

    An escape hatch for exposing a route without a session when no module owns
    it. Each entry is treated as a prefix rule and seeded into the
    ``PublicRouteRegistry`` at boot. Modules should prefer the
    ``register_public_routes`` hook, which is method-aware.
    """

    @field_validator("database_url", mode="after")
    @classmethod
    def _anchor_relative_sqlite_path(cls, value: str) -> str:
        return _absolutize_sqlite_url(value, anchor=_project_anchor(_ENV_FILE))

    @field_validator("auth_provider", mode="after")
    @classmethod
    def _normalize_auth_provider(cls, value: str) -> str:
        """Strip whitespace; treat blank as unset.

        ``SM_AUTH_PROVIDER=`` in a ``.env`` yields ``''``, which matches no
        installed provider and would mount all of them. The out-of-process
        readers (``make doctor``, ``gen-pages``) go through
        ``resolve_auth_provider``, which already falls back on blank — without
        this they and the host would disagree about the active provider.
        """
        return value.strip() or DEFAULT_AUTH_PROVIDER

    @field_validator("trusted_proxy", mode="after")
    @classmethod
    def _normalize_trusted_proxy(cls, value: str | None) -> str | None:
        """Strip surrounding whitespace; treat blank as unset.

        Guards against a stray space silently defeating the feature: uvicorn
        decides ``*``-trust by comparing the *raw* string to ``"*"`` before it
        strips, so ``"* "`` would be parsed as a literal host that matches no
        client — re-introducing GH #223 with no error. Blank → ``None`` so the
        middleware isn't installed at all.
        """
        if value is None:
            return None
        return value.strip() or None

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @model_validator(mode="after")
    def _forbid_placeholder_secret_in_production(self) -> BootstrapSettings:
        if (
            self.environment not in NON_PROD_ENVIRONMENTS
            and self.secret_key == _PLACEHOLDER_SECRET_KEY
        ):
            raise ValueError(
                f"SM_SECRET_KEY must be set to a non-default value when "
                f"SM_ENVIRONMENT={self.environment!r}. Generate one with "
                "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`."
            )
        return self
