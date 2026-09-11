"""Prop resolution — the v3 rules in one place.

Input: the page's props, the shared props, the component being rendered and
the typed request. Output: the resolved values plus every piece of metadata
the page object announces (deferred groups, merge strategies, once keys,
scroll cursors, shared keys). Nothing here knows about HTTP.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from simple_module_inertia.props import Prop, as_prop, resolve_value
from simple_module_inertia.request import InertiaRequest


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


async def _deep_resolve(value: Any) -> Any:
    """Resolve callables/awaitables/Props anywhere inside a container."""
    value = await resolve_value(value)
    if isinstance(value, dict):
        return {k: await _deep_resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [await _deep_resolve(v) for v in value]
    return value


def _wants(name: str, prop: Prop, req: InertiaRequest, partial: bool) -> bool:
    """Should this prop's value be resolved for this response?"""
    if prop.is_once and name in req.except_once_props:
        return False
    if prop.always:
        return True
    if partial:
        if req.partial_data and name not in req.partial_data:
            return False
        return name not in req.partial_except
    return prop.optional is False and prop.deferred_group is None


def _announce_merge(name: str, prop: Prop, req: InertiaRequest, out: ResolvedProps) -> None:
    if name in req.reset:
        return
    mode = prop.merge_mode
    if prop.scroll is not None:
        mode = req.merge_intent or "append"
    if mode == "append":
        out.merge.append(name)
    elif mode == "prepend":
        out.prepend.append(name)
    elif mode == "deep":
        out.deep_merge.append(name)
    else:
        return
    if prop.match_on:
        out.match_on.append(f"{name}.{prop.match_on}")


async def resolve_props(
    page_props: Mapping[str, Any],
    shared_props: Mapping[str, Any],
    component: str,
    req: InertiaRequest,
) -> ResolvedProps:
    out = ResolvedProps()
    partial = req.is_partial_for(component)
    combined: dict[str, Any] = {**shared_props, **page_props}

    for name, raw in combined.items():
        prop = as_prop(raw)
        if not partial and prop.deferred_group is not None:
            out.deferred.setdefault(prop.deferred_group, []).append(name)
        if prop.merge_mode is not None or prop.scroll is not None:
            _announce_merge(name, prop, req, out)
        if not _wants(name, prop, req, partial):
            continue
        out.props[name] = await _deep_resolve(prop)
        if prop.is_once:
            key = prop.once_key or name
            out.once[key] = {"prop": name, "expiresAt": prop.once_expires_at}
        if prop.scroll is not None:
            out.scroll[name] = prop.scroll.as_page_object()

    out.shared = [k for k in shared_props if k in out.props and k not in page_props]
    return out
