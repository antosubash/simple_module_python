"""Prop wrappers.

One frozen ``Prop`` carries every v3 flag; each factory sets one of them and
accepts either a raw value or an existing ``Prop``, so wrappers compose by
stacking: ``merge(defer(load_feed), match_on="id")``. The resolver reads the
flags; nothing here talks to a request.
"""

from __future__ import annotations

import inspect
import warnings
from dataclasses import dataclass, replace
from typing import Any, Literal

MergeMode = Literal["append", "prepend", "deep"]


@dataclass(frozen=True)
class ScrollMeta:
    """Infinite-scroll cursor metadata, reported under ``scrollProps``."""

    page_name: str
    current_page: int
    previous_page: int | None
    next_page: int | None
    reset: bool = False

    def as_page_object(self) -> dict[str, Any]:
        return {
            "pageName": self.page_name,
            "currentPage": self.current_page,
            "previousPage": self.previous_page,
            "nextPage": self.next_page,
            "reset": self.reset,
        }


@dataclass(frozen=True)
class Prop:
    value: Any
    optional: bool = False
    always: bool = False
    deferred_group: str | None = None
    merge_mode: MergeMode | None = None
    match_on: str | None = None
    once_key: str | None = None
    once_expires_at: int | None = None
    scroll: ScrollMeta | None = None
    # ``once(value)`` with no key still marks the prop as once; the key defaults
    # to the prop name at resolve time. A private flag keeps that distinction
    # without making ``once_key`` a sentinel.
    _once_flag: bool = False

    @property
    def is_once(self) -> bool:
        return self._once_flag


def as_prop(value: Any) -> Prop:
    return value if isinstance(value, Prop) else Prop(value)


def optional(value: Any) -> Prop:
    return replace(as_prop(value), optional=True)


def always(value: Any) -> Prop:
    return replace(as_prop(value), always=True)


def defer(value: Any, group: str = "default") -> Prop:
    return replace(as_prop(value), deferred_group=group)


def merge(value: Any, match_on: str | None = None) -> Prop:
    return replace(as_prop(value), merge_mode="append", match_on=match_on)


def prepend(value: Any, match_on: str | None = None) -> Prop:
    return replace(as_prop(value), merge_mode="prepend", match_on=match_on)


def deep_merge(value: Any, match_on: str | None = None) -> Prop:
    return replace(as_prop(value), merge_mode="deep", match_on=match_on)


def once(value: Any, key: str | None = None, expires_at: int | None = None) -> Prop:
    return replace(as_prop(value), once_key=key, once_expires_at=expires_at, _once_flag=True)


def scroll(
    value: Any,
    *,
    page_name: str,
    current_page: int,
    previous_page: int | None,
    next_page: int | None,
    reset: bool = False,
) -> Prop:
    if not page_name:
        raise ValueError("scroll() requires a non-empty page_name")
    meta = ScrollMeta(page_name, current_page, previous_page, next_page, reset)
    return replace(as_prop(value), scroll=meta)


def lazy(value: Any) -> Prop:
    """Deprecated alias kept for callers migrating from fastapi-inertia."""
    warnings.warn("lazy() is deprecated; use optional()", DeprecationWarning, stacklevel=2)
    return optional(value)


async def resolve_value(value: Any) -> Any:
    """Unwrap a ``Prop``, call a callable, await an awaitable — recursively."""
    if isinstance(value, Prop):
        value = value.value
    if callable(value):
        value = value()
    if inspect.isawaitable(value):
        value = await value
    return value
