"""Minimal ``.env`` parser + env-var helpers — dependency-free.

Used in places that can't or shouldn't pull in ``pydantic-settings`` (the
diagnostics CLI runs before the host package is imported; the users-module
bootstrap runs after settings are constructed and needs to read values that
``UsersSettings`` deliberately omits from ``env_file``).
"""

from __future__ import annotations

import os
from pathlib import Path

BOOL_LITERALS_TRUE = frozenset({"1", "true", "t", "yes", "y", "on"})
BOOL_LITERALS_FALSE = frozenset({"0", "false", "f", "no", "n", "off"})

# How many parent directories to probe for a `.env` above the cwd. One level
# covers the workspace layout (`host/` → root); a couple more cover running
# from `modules/<name>/`. Bounded so an unrelated `.env` far up the tree
# (e.g. in $HOME) is never picked up by accident.
_ENV_WALK_LIMIT = 4


def find_env_file() -> Path:
    """Locate the project ``.env`` regardless of which subdirectory runs us.

    ``$SM_PROJECT_ROOT/.env`` wins when set. Otherwise walk up from the cwd:
    the web process chdirs to the workspace root so this finds ``./.env``
    immediately, while a CLI invoked from ``host/`` or ``modules/<name>/``
    finds the same file its app uses instead of silently loading nothing.
    Falls back to a cwd-relative ``Path(".env")`` when nothing is found.

    This is the one .env-resolution convention for the whole ecosystem: the
    settings layer (``BootstrapSettings``) and every out-of-process tool
    (diagnostics CLI, worker entrypoints, users bootstrap) resolve through
    here, so they can never disagree about which file is in effect.
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
        # A `.git` or `.env.example` marks a project root: never ascend past
        # one, or a nested checkout (a git worktree, a repo inside another
        # repo, a fresh scaffold — which ships `.env.example` before any
        # `.git` exists) would silently load the *outer* project's `.env`.
        if (candidate / ".git").exists() or (candidate / ".env.example").is_file():
            break
    return Path(".env")


def parse_dotenv(path: Path | None = None) -> dict[str, str]:
    """Parse a ``.env`` file into a dict. Empty dict if the file is missing.

    Values surrounded by matching single or double quotes have the quotes
    stripped. Does *not* handle escapes, ``export KEY=…``, or multiline
    values — keep the file simple. Does *not* mutate ``os.environ``; the
    caller decides whether to merge.

    Without ``path``, resolves via :func:`find_env_file` — the convention
    used by every tool in this repo.
    """
    if path is None:
        path = find_env_file()
    if not path.is_file():
        return {}
    parsed: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        parsed[key.strip()] = value.strip().strip('"').strip("'")
    return parsed


def load_dotenv_into_environ(path: Path | None = None) -> None:
    """Merge ``parse_dotenv(path)`` into ``os.environ`` via ``setdefault``.

    Same precedence as the web process under uvicorn: real environment wins
    over file values. Worker entrypoints call this before importing settings.
    """
    for key, value in parse_dotenv(path).items():
        os.environ.setdefault(key, value)


def env_str(name: str, default: str) -> str:
    """Return ``$name`` if set and non-empty, else ``default``."""
    value = os.environ.get(name, "").strip()
    return value or default


def env_bool(name: str, default: bool = False) -> bool:
    """Parse ``$name`` as a boolean, returning ``default`` when unset/blank."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in BOOL_LITERALS_TRUE:
        return True
    if raw in BOOL_LITERALS_FALSE:
        return False
    return default
