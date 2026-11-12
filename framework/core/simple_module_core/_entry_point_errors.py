"""Telling an unimportable module entry point apart from a broken module."""

from __future__ import annotations


def own_package_missing(ep, exc: BaseException) -> bool:
    """Whether the entry point's own package, not a dependency, is unimportable.

    A package installed after this process started looks like that: the entry
    point is listed (metadata is read fresh) but ``sys.path`` was fixed at
    start-up, so an editable install's ``.pth`` entry is not on it (GH #915).
    """
    if not isinstance(exc, ModuleNotFoundError) or not exc.name:
        return False
    target = getattr(ep, "module", "") or ""
    return target == exc.name or target.startswith(f"{exc.name}.")


def stale_path_message(ep, exc: ModuleNotFoundError) -> str:
    return (
        f"Module entry point '{ep.name}' is installed but {exc.name!r} cannot be imported "
        "in this process. If it was added after the server started (smpy add, uv sync), "
        "restart `make dev`: a reload keeps the old import path"
    )
