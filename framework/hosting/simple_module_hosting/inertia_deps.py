"""Lazy Inertia dependency that resolves from app state at request time."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from simple_module_inertia import INERTIA_HEADER, Inertia, is_inertia_request

from simple_module_hosting._inertia_shared import resolve_inertia_shared
from simple_module_hosting.token_guard import GATE_PAGE, mark_token_gate


async def get_inertia(request: Request) -> Inertia:
    """Resolve the Inertia instance from the app's configured dependency.

    This allows view endpoints to declare ``inertia: InertiaDep`` without
    needing the Inertia config at import time.
    """
    inertia_dep = request.app.state.inertia_dependency
    inertia = inertia_dep(request, None)

    shared = await resolve_inertia_shared(request)
    if shared:
        inertia.share(**shared)

    return inertia


# A route rendering a page refuses API tokens even behind a permission gate
# (``token_guard``): its props are a second, unscoped read API.
mark_token_gate(get_inertia, GATE_PAGE)

InertiaDep = Annotated[Inertia, Depends(get_inertia)]


# Re-exported so modules detect an Inertia visit the same way the adapter does
# without depending on simple_module_inertia directly.
__all__ = ["INERTIA_HEADER", "InertiaDep", "get_inertia", "is_inertia_request"]
