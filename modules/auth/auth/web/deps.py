"""FastAPI auth dependencies — get_current_user, CurrentUser."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from simple_module_hosting.i18n_deps import TranslatorDep

from auth.contracts.schemas import UserContext


async def get_current_user(request: Request, t: TranslatorDep) -> UserContext:
    """Extract the authenticated user from request state.

    The auth middleware must set ``request.state.user`` before this runs.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail=t.t("auth.errors.not_authenticated"))
    return user


CurrentUser = Annotated[UserContext, Depends(get_current_user)]
