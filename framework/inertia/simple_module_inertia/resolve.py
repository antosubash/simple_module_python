"""Prop resolution — the v3 rules in one place.

Input: the page's props, the shared props, the component being rendered and
the typed request. Output: the resolved values plus every piece of metadata
the page object announces. Nothing here knows about HTTP.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from simple_module_inertia.props import Prop, as_prop, resolve_value
from simple_module_inertia.request import InertiaRequest

logger = logging.getLogger(__name__)

_SCALARS = frozenset({str, int, float, bool, type(None)})


def _is_dynamic(value: Any) -> bool:
    """A Prop, loader or awaitable: something the resolver must unwrap."""
    return isinstance(value, Prop) or callable(value) or inspect.isawaitable(value)


@dataclass
class ResolvedProps:
    props: dict[str, Any] = field(default_factory=dict)
    deferred: dict[str, list[str]] = field(default_factory=dict)
    merge: list[str] = field(default_factory=list)
    prepend: list[str] = field(default_factory=list)
    deep_merge: list[str] = field(default_factory=list)
    match_on: list[str] = field(default_factory=list)
    once: dict[str, dict[str, Any]] = field(default_factory=dict)
    scroll: dict[str, dict[str, Any]] = field(default_factory=dict)
    shared: list[str] = field(default_factory=list)
    rescued: list[str] = field(default_factory=list)


def _matches(path: str, filters: frozenset[str]) -> bool:
    return any(path == key or path.startswith(f"{key}.") for key in filters)


def _included(path: str, req: InertiaRequest, *, ancestors: bool = False) -> bool:
    """Does the partial reload select ``path``? ``ancestors`` also accepts a path
    that only *contains* a selected path (``auth`` for ``auth.user``), so its
    children can be filtered; metadata labels must not use it."""
    if (
        req.partial_data
        and not _matches(path, req.partial_data)
        and (not ancestors or not any(key.startswith(f"{path}.") for key in req.partial_data))
    ):
        return False
    return not _matches(path, req.partial_except)


def _announce_merge(
    name: str, prop: Prop, req: InertiaRequest, out: ResolvedProps, value: Any = None
) -> None:
    if name in req.reset or (prop.scroll is not None and prop.scroll.reset):
        return
    mode = prop.merge_mode
    path = name
    if prop.scroll is not None:
        mode = req.merge_intent or "append"
        # A resolved bare list is itself the page of items: merge at its root.
        if prop.scroll.wrapper is not None and not isinstance(value, list):
            path = f"{name}.{prop.scroll.wrapper}"
    if mode == "append":
        out.merge.append(path)
    elif mode == "prepend":
        out.prepend.append(path)
    elif mode == "deep":
        out.deep_merge.append(path)
    else:
        return
    if prop.match_on:
        out.match_on.append(f"{path}.{prop.match_on}")


def _announce_metadata(
    name: str,
    prop: Prop,
    req: InertiaRequest,
    partial: bool,
    out: ResolvedProps,
    parent_resolved: bool = False,
    value: Any = None,
) -> None:
    # ``always`` props and children of an already-resolved value are sent whole,
    # so their merge/once labels must accompany them.
    if partial and not (parent_resolved or prop.always or _included(name, req)):
        return
    _announce_merge(name, prop, req, out, value)
    if prop.is_once:
        _announce_once(name, prop, out)


def _announce_once(path: str, prop: Prop, out: ResolvedProps) -> None:
    out.once[prop.once_key or path] = {"prop": path, "expiresAt": prop.once_expires_at}


async def _resolve_tree(
    props: Mapping[str, Any],
    req: InertiaRequest,
    partial: bool,
    out: ResolvedProps,
    prefix: str = "",
    parent_resolved: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    filtering = partial and not parent_resolved
    for key, raw in props.items():
        # Fast path: plain JSON leaves and containers carry no prop flags, so
        # they skip the Prop wrapper; only a partial filter needs their path.
        if not _is_dynamic(raw):
            if type(raw) in _SCALARS and not filtering:
                result[key] = raw
                continue
            path = f"{prefix}.{key}" if prefix else key
            if filtering and not _included(path, req, ancestors=True):
                continue
            result[key] = await _resolve_children(raw, path, req, partial, out, parent_resolved)
            continue
        path = f"{prefix}.{key}" if prefix else key
        prop = as_prop(raw)
        if partial and not (parent_resolved or prop.always or _included(path, req, ancestors=True)):
            continue
        if not partial:
            cached = prop.is_once and (prop.once_key or path) in req.except_once_props
            # Inside a resolved loader value or a list there is no addressable
            # path for a follow-up request, so such props resolve eagerly.
            if not parent_resolved and (prop.optional or prop.deferred_group is not None):
                if prop.deferred_group is not None and not cached:
                    out.deferred.setdefault(prop.deferred_group, []).append(path)
                _announce_metadata(path, prop, req, False, out)
                continue
            if cached:
                _announce_once(path, prop, out)
                continue
        try:
            value = await resolve_value(raw)
        except Exception:
            if not prop.rescue:
                raise
            logger.exception("Failed to resolve Inertia prop %s", path)
            out.rescued.append(path)
            continue
        _announce_metadata(path, prop, req, partial, out, parent_resolved, value)
        if prop.scroll is not None:
            out.scroll[path] = {
                **prop.scroll.as_page_object(),
                "reset": prop.scroll.reset or path in req.reset,
            }
        # A loader's value is returned whole: partial filters stop at its path.
        result[key] = await _resolve_children(value, path, req, partial, out, True)
    return result


async def _resolve_children(
    value: Any,
    path: str,
    req: InertiaRequest,
    partial: bool,
    out: ResolvedProps,
    bypass: bool,
) -> Any:
    if isinstance(value, dict):
        return await _resolve_tree(value, req, partial, out, path, bypass)
    if isinstance(value, list):
        items: list[Any] = []
        for index, child in enumerate(value):
            if type(child) in _SCALARS or not (
                _is_dynamic(child) or isinstance(child, (dict, list))
            ):
                items.append(child)
                continue
            resolved = await _resolve_tree({str(index): child}, req, partial, out, path, True)
            items.extend(resolved.values())
        return items
    return value


async def resolve_props(
    page_props: Mapping[str, Any],
    shared_props: Mapping[str, Any],
    component: str,
    req: InertiaRequest,
) -> ResolvedProps:
    out = ResolvedProps()
    partial = req.is_partial_for(component)
    combined: dict[str, Any] = {**shared_props, **page_props}
    out.props = await _resolve_tree(combined, req, partial, out)
    out.shared = [k for k in shared_props if k in out.props and k not in page_props]
    return out
