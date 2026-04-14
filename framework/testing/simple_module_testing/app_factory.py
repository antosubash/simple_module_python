"""Build a minimal FastAPI app wrapping a single module for isolated testing."""

from __future__ import annotations

from fastapi import FastAPI
from simple_module_core import ModuleBase
from simple_module_hosting.app_builder import wire_module_routes


def build_test_app(module: ModuleBase | type[ModuleBase]) -> FastAPI:
    """Return a FastAPI app that registers only the given module's routes.

    Accepts either a module class (instantiated lazily) or a pre-built
    instance. The resulting app has the module's registered routes and
    empty framework registries so tests don't need the full
    :func:`simple_module_hosting.create_app` machinery.
    """
    instance = module() if isinstance(module, type) else module

    app = FastAPI()
    app.state.module = instance
    wire_module_routes(app, instance)
    return app
