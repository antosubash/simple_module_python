"""Locate optional conventional modules without hiding broken imports."""

from __future__ import annotations

from importlib.util import find_spec


def has_conventional_module(package: str, suffix: str) -> bool:
    name = f"{package}.{suffix}"
    try:
        return find_spec(name) is not None
    except ModuleNotFoundError as exc:
        # find_spec imports parents; only an absent parent means no endpoint.
        if exc.name and name.startswith(f"{exc.name}."):
            return False
        raise
