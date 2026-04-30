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


def parse_dotenv(path: Path | None = None) -> dict[str, str]:
    """Parse a ``.env`` file into a dict. Empty dict if the file is missing.

    Values surrounded by matching single or double quotes have the quotes
    stripped. Does *not* handle escapes, ``export KEY=…``, or multiline
    values — keep the file simple. Does *not* mutate ``os.environ``; the
    caller decides whether to merge.

    Without ``path``, looks up ``$SM_PROJECT_ROOT/.env`` (falling back to
    ``$CWD/.env``) — the convention used by every tool in this repo.
    """
    if path is None:
        root = Path(os.environ.get("SM_PROJECT_ROOT") or Path.cwd())
        path = root / ".env"
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
