"""Lazy Inertia dependency that resolves from app state at request time."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from inertia import Inertia


async def get_inertia(request: Request) -> Inertia:
    """Resolve the Inertia instance from the app's configured dependency.

    This allows view endpoints to declare ``inertia: InertiaDep`` without
    needing the Inertia config at import time.
    """
    inertia_dep = request.app.state.inertia_dependency
    return inertia_dep(request, None)


InertiaDep = Annotated[Inertia, Depends(get_inertia)]
