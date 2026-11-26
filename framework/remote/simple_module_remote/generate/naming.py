"""CLI group and command names derived from OpenAPI tags and operationIds."""

from __future__ import annotations

import re

__all__ = [
    "RESERVED",
    "command_name",
    "group_name",
    "kebab_name",
    "snake_name",
    "valid_command_name",
]

RESERVED: frozenset[str] = frozenset(
    {"env", "login", "logout", "whoami", "doctor", "schema", "api", "raw"}
)

UNTAGGED_GROUP = "host"
# What an `x-cli-name` override may be: the same alphabet derived names use.
_COMMAND_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


def valid_command_name(name: str) -> bool:
    return bool(_COMMAND_NAME.fullmatch(name))


def snake_name(name: str) -> str:
    """Snake-case a name, mirroring the server's operationId module prefix.

    ``FeatureFlags`` -> ``feature_flags``, ``X-Foo`` -> ``x_foo``.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", spaced).strip("_").lower()


def kebab_name(name: str) -> str:
    return snake_name(name).replace("_", "-")


def group_name(tag: str | None) -> str:
    """``FeatureFlags`` -> ``feature-flags``; no tag -> ``host``."""
    if not tag:
        return UNTAGGED_GROUP
    return kebab_name(tag) or UNTAGGED_GROUP


def command_name(
    operation_id: str,
    tag: str | None,
    override: str | None,
    *,
    method: str = "",
    path: str = "",
) -> str:
    """Strip the ``<snake(tag)>_`` prefix and kebab-case the rest; a valid ``override`` wins.

    Never returns an empty string: an id with no usable characters falls back to the
    kebab of ``<method>-<path>``, then to ``operation``.
    """
    if override and valid_command_name(override):
        return override
    rest = operation_id
    if tag:
        prefix = f"{snake_name(tag)}_"
        if rest.startswith(prefix) and len(rest) > len(prefix):
            rest = rest[len(prefix) :]
    return kebab_name(rest) or kebab_name(f"{method}_{path}") or "operation"
