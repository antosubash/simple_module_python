"""Exact paths and directory prefixes for framework request gates."""


def matches_path(path: str, *, exact: tuple[str, ...] = (), prefixes: tuple[str, ...] = ()) -> bool:
    """Match exact paths or prefixes ending in a slash."""
    if any(not prefix.endswith("/") for prefix in prefixes):
        raise ValueError("Path prefixes must end with '/'.")
    return path in exact or path.startswith(prefixes)
