"""OIDC role-claim lookup."""

from typing import Any


def extract_nested(data: dict, path: str) -> list[str] | None:
    # A claim named exactly ``path`` wins: Auth0/Okta namespace custom claims
    # as URLs (``https://example.com/roles``), which contain dots.
    if path in data:
        value = data[path]
        return value if isinstance(value, list) else None
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current if isinstance(current, list) else None
