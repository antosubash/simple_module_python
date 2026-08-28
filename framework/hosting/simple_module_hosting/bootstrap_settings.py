"""Env-only settings read before the database is available.

What is left here is what cannot come from the database without a
chicken-and-egg problem, plus the two facts about the *process* rather than
the deployment:

- ``database_url`` opens the database, so it cannot be stored in it.
- ``modules_enabled`` decides which modules load, and the settings module is
  itself one of them.
- ``environment``, ``debug`` and ``vite_dev_url`` describe how this process
  was launched, not how the application is configured.

Everything else moved to :class:`~simple_module_hosting.host_settings.HostSettings`
and is read from the DB by ``_preapp_config.merge_host_settings`` before
``create_app`` builds anything. Env still wins over a DB value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.dotenv import find_env_file
from simple_module_core.environments import NON_PROD_ENVIRONMENTS

_PLACEHOLDER_SECRET_KEY = "change-me-in-production"


def _absolutize_sqlite_url(url: str, *, anchor: Path) -> str:
    """Rewrite a relative sqlite path to an absolute one under ``anchor``.

    ``sqlite+aiosqlite:///./host/app.db`` means "relative to the project
    root" by convention, but SQLAlchemy resolves it against the process cwd
    — correct in the web process (which chdirs) and silently wrong in every
    CLI run from a subdirectory. Absolute paths (``:////...``), ``:memory:``,
    SQLite URI-mode paths (``file:...?uri=true``), and non-sqlite URLs pass
    through untouched.
    """
    if not url.startswith("sqlite"):
        return url
    scheme, sep, rest = url.partition(":///")
    if not sep or not rest or rest.startswith(("/", ":memory:", "file:")):
        return url
    path_part, query_sep, query = rest.partition("?")
    resolved = (anchor / path_part).resolve()
    return f"{scheme}:///{resolved}{query_sep}{query}"


class BootstrapSettings(BaseSettings):
    """Pre-DB bootstrap environment knobs."""

    model_config = SettingsConfigDict(env_prefix="SM_", env_file=".env", extra="ignore")

    def __init__(self, **values: Any) -> None:
        # Discover the project `.env` per instantiation (a handful of stat
        # calls), never at import time: a process may import this module and
        # only later chdir or set SM_PROJECT_ROOT. Only when the caller
        # hasn't already decided — a plain `dict.setdefault(k, find_env_file())`
        # would evaluate find_env_file() unconditionally as part of the call,
        # even when `_env_file` is already in `values`, paying for a walk it
        # throws away. This also has to preserve pydantic-settings' documented
        # `_env_file=None` idiom ("load no .env file at all") rather than
        # silently overriding it.
        if "_env_file" not in values:
            values["_env_file"] = find_env_file()
        env_file = values["_env_file"]
        super().__init__(**values)
        # Anchor discovery is independent of whether an env file is loaded:
        # a caller passing `_env_file=None` still needs relative sqlite paths
        # anchored at the discovered project root, not the process cwd —
        # otherwise that idiom would silently point sqlite at whatever
        # directory happened to be cwd. The same discovered path anchors
        # relative sqlite paths below, so the env values and the sqlite
        # anchor can never come from two different projects.
        anchor = (
            Path(env_file).parent if isinstance(env_file, (str, Path)) else find_env_file().parent
        )
        self.database_url = _absolutize_sqlite_url(self.database_url, anchor=anchor)

    database_url: str = "sqlite+aiosqlite:///./app.db"

    environment: str = "development"
    secret_key: str = _PLACEHOLDER_SECRET_KEY
    vite_dev_url: str = "http://localhost:5050"
    debug: bool = False

    modules_enabled: list[str] | None = None

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @model_validator(mode="after")
    def _forbid_placeholder_secret_in_production(self) -> BootstrapSettings:
        """Reject the shipped placeholder in production.

        Only fires when the key is *explicitly* the placeholder. An absent key
        is valid now: ``ensure_secret_key`` generates one and persists it, so
        a production boot no longer fails just because nobody set this.
        """
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
