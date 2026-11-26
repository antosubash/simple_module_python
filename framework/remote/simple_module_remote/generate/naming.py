"""CLI group and command names derived from OpenAPI tags and operationIds."""

from __future__ import annotations

import re

__all__ = ["RESERVED", "command_name", "group_name"]

RESERVED: frozenset[str] = frozenset(
    {"env", "login", "logout", "whoami", "doctor", "schema", "api", "raw"}
)

UNTAGGED_GROUP = "host"


def _snake(name: str) -> str:
    """Mirror the server's operationId module prefix (``FeatureFlags`` -> ``feature_flags``)."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", spaced).strip("_").lower()


def _kebab(name: str) -> str:
    return _snake(name).replace("_", "-")


def group_name(tag: str | None) -> str:
    """``FeatureFlags`` -> ``feature-flags``; no tag -> ``host``."""
    if not tag:
        return UNTAGGED_GROUP
    return _kebab(tag) or UNTAGGED_GROUP


def command_name(operation_id: str, tag: str | None, override: str | None) -> str:
    """Strip the ``<snake(tag)>_`` prefix and kebab-case the rest; ``override`` wins."""
    if override:
        return override
    rest = operation_id
    if tag:
        prefix = f"{_snake(tag)}_"
        if rest.startswith(prefix) and len(rest) > len(prefix):
            rest = rest[len(prefix) :]
    return _kebab(rest)
