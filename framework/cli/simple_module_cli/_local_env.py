"""Split a new app's env file into a committed template and a local ``.env``.

``.env.example`` is committed, so it only ever carries placeholders. The
secrets ``smpy new`` generates go to ``.env``, which every scaffold's
``.gitignore`` excludes (GH #441). An existing ``.env`` is never overwritten:
only keys it does not define yet are added.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable
from pathlib import Path

from simple_module_cli._env import env_values, set_env_key

__all__ = ["add_postgres_password_placeholder", "comment_out_env_key", "write_local_env"]

_PG_PASSWORD_NOTE = (
    "# Compose puts this into SM_DATABASE_URL unencoded: use only URL-safe\n"
    "# characters (letters, digits, - _ . ~). `make docker-up` rejects others (GH #472).\n"
)

_SECRET_NOTE = (
    "# Secrets — `smpy new` generated these into .env (gitignored); keep them\n"
    "# out of this committed file. Set real values wherever you deploy."
)


def comment_out_env_key(text: str, key: str) -> str:
    """Turn ``KEY=...`` into a bare ``# KEY=`` placeholder, in place if present."""
    lines = text.splitlines()
    placeholder = f"# {key}="
    hits = [i for i, ln in enumerate(lines) if ln.startswith((f"{key}=", placeholder))]
    if hits:
        lines[hits[0]] = placeholder
        lines = [ln for i, ln in enumerate(lines) if i not in hits[1:]]
    else:
        if _SECRET_NOTE.splitlines()[0] not in lines:
            lines += ["", *_SECRET_NOTE.splitlines()]
        lines.append(placeholder)
    return "\n".join(lines) + "\n"


def add_postgres_password_placeholder(text: str) -> str:
    """Add an empty ``POSTGRES_PASSWORD=`` to ``.env.example``, with its URL-safe note."""
    text = set_env_key(text, "POSTGRES_PASSWORD", "")
    return text.replace("POSTGRES_PASSWORD=\n", _PG_PASSWORD_NOTE + "POSTGRES_PASSWORD=\n", 1)


def write_local_env(
    target: Path, *, secret_keys: Iterable[str], overrides: dict[str, str] | None = None
) -> None:
    """Write ``target/.env`` from ``.env.example`` plus generated secrets.

    ``secret_keys`` get a fresh random value each; ``overrides`` are written
    verbatim (e.g. a database URL carrying a generated password). Overrides
    belong together, so an existing ``.env`` defining any of them gets none:
    a fresh URL must not disagree with a kept ``POSTGRES_PASSWORD``.
    """
    env_path = target / ".env"
    existing = env_path.exists()
    source = env_path if existing else target / ".env.example"
    text = source.read_text(encoding="utf-8") if source.exists() else ""
    defined = env_values(text).keys()
    overrides = overrides or {}
    if existing and defined & overrides.keys():
        overrides = {}
    values = {key: secrets.token_urlsafe(32) for key in secret_keys} | overrides
    for key, value in values.items():
        if existing and key in defined:
            continue
        placeholder = f"# {key}="
        lines = text.splitlines()
        if placeholder in lines:
            # Line-based, so a placeholder on the last line (no trailing
            # newline) is handled too.
            lines[lines.index(placeholder)] = f"{key}={value}"
            text = "\n".join(lines) + "\n"
        else:
            text = set_env_key(text, key, value)
    env_path.write_text(text, encoding="utf-8")
    env_path.chmod(0o600)  # holds generated secrets
