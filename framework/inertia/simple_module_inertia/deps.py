"""Build the per-request dependency hosting publishes on ``app.state``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Request

from simple_module_inertia.config import InertiaConfig
from simple_module_inertia.inertia import Inertia
from simple_module_inertia.templating import InertiaExtension


def inertia_dependency_factory(config: InertiaConfig) -> Callable[..., Inertia]:
    env = config.templates.env
    if InertiaExtension not in env.extensions.values():
        env.add_extension(InertiaExtension)

    def inertia_dependency(request: Request, client: Any = None) -> Inertia:
        return Inertia(request, config, client)

    return inertia_dependency
