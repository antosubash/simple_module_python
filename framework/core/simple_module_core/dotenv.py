"""Minimal ``.env`` parser — dependency-free.

Used in places that can't or shouldn't pull in ``pydantic-settings`` (the
diagnostics CLI runs before the host package is imported; the users-module
bootstrap runs after settings are constructed and needs to read values that
``UsersSettings`` deliberately omits from ``env_file``).
"""

from __future__ import annotations

import os
from pathlib import Path


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
