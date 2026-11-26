"""Split ``key=value`` command-line items."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import click

__all__ = ["split_pair", "split_pairs"]


def split_pair(item: str, flag: str, error: type[Exception]) -> tuple[str, str]:
    """``key=value`` -> ``(key, value)``; raises ``error`` naming ``flag`` otherwise."""
    key, sep, value = item.partition("=")
    if not sep or not key:
        raise error(f"{flag}: expected key=value, got {item!r}")
    return key, value


def split_pairs(items: Iterable[Any] | None, flag: str) -> list[tuple[str, str]]:
    return [split_pair(str(item), flag, click.UsageError) for item in items or ()]
