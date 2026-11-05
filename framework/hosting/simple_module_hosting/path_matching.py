"""Exact paths and directory prefixes for framework request gates."""


def validated_prefixes(*prefixes: str) -> tuple[str, ...]:
    """Validate directory boundaries once when building a gate's prefixes."""
    if any(not prefix.endswith("/") for prefix in prefixes):
        raise ValueError("Path prefixes must end with '/'.")
    return prefixes


def matches_path(path: str, *, exact: tuple[str, ...] = (), prefixes: tuple[str, ...] = ()) -> bool:
    """Match exact paths or directory prefixes built with ``validated_prefixes``."""
    return path in exact or path.startswith(prefixes)
