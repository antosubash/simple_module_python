"""Development-only Inertia v3 fixture routes for the browser e2e suite.

The framework's own pages never use partial reloads, deferred props, merge
props, once props, infinite scroll, error bags, history encryption,
``WhenVisible``, polling or prefetch. These routes exist so
``tests/e2e/inertia/`` can drive those client features in a real
browser. The host mounts them only when ``settings.is_development`` is true.
"""

from typing import Protocol

from fastapi import APIRouter, Depends, FastAPI
from simple_module_hosting.token_guard import Authenticated

from host.e2e_inertia import features, forms, navigation
from host.e2e_inertia.constants import ROUTE_PREFIX


def build_router() -> APIRouter:
    """Return the fixture router; every route needs a signed-in user."""
    router = APIRouter(
        prefix=ROUTE_PREFIX,
        include_in_schema=False,
        dependencies=[Depends(Authenticated())],
    )
    router.include_router(features.router)
    router.include_router(forms.router)
    router.include_router(navigation.router)
    return router


class _HasIsDevelopment(Protocol):
    @property
    def is_development(self) -> bool: ...


def mount_if_development(app: FastAPI, settings: _HasIsDevelopment) -> bool:
    """Mount the fixture routes on ``app`` only in development; report whether it did."""
    if not settings.is_development:
        return False
    app.include_router(build_router())
    return True
