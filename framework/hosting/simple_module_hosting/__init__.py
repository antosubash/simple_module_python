"""SimpleModule Hosting - App builder, module loader, middleware pipeline."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simple_module_hosting.boot.app_builder import create_app as create_app
    from simple_module_hosting.config._preapp_config import (
        merge_host_settings as merge_host_settings,
    )
    from simple_module_hosting.config.settings import Settings as Settings
    from simple_module_hosting.error_handling.errors import render_error_page as render_error_page
    from simple_module_hosting.frontend.shared_props import (
        SharedPropsProvider as SharedPropsProvider,
    )
    from simple_module_hosting.frontend.shared_props import (
        register_inertia_shared_provider as register_inertia_shared_provider,
    )
    from simple_module_hosting.frontend.shared_props import (
        replace_inertia_shared_prop as replace_inertia_shared_prop,
    )
    from simple_module_hosting.observability.logging import correlation_id as correlation_id
    from simple_module_hosting.observability.logging import setup_logging as setup_logging
    from simple_module_hosting.pipeline.middleware_config import MiddlewareStage as MiddlewareStage
    from simple_module_hosting.pipeline.middleware_config import add_middleware as add_middleware
    from simple_module_hosting.pipeline.middleware_config import (
        disable_middleware as disable_middleware,
    )
    from simple_module_hosting.pipeline.middleware_config import (
        replace_middleware as replace_middleware,
    )

__all__ = [
    "MiddlewareStage",
    "Settings",
    "SharedPropsProvider",
    "add_middleware",
    "correlation_id",
    "create_app",
    "disable_middleware",
    "merge_host_settings",
    "register_inertia_shared_provider",
    "render_error_page",
    "replace_inertia_shared_prop",
    "replace_middleware",
    "setup_logging",
]

_EXPORT_MODULES = {
    "MiddlewareStage": "pipeline.middleware_config",
    "add_middleware": "pipeline.middleware_config",
    "disable_middleware": "pipeline.middleware_config",
    "replace_middleware": "pipeline.middleware_config",
    "Settings": "config.settings",
    "SharedPropsProvider": "frontend.shared_props",
    "correlation_id": "observability.logging",
    "create_app": "boot.app_builder",
    "merge_host_settings": "config._preapp_config",
    "register_inertia_shared_provider": "frontend.shared_props",
    "replace_inertia_shared_prop": "frontend.shared_props",
    "render_error_page": "error_handling.errors",
    "setup_logging": "observability.logging",
}


def __getattr__(name: str):
    # The host factory must load dotenv before importing settings or app_builder.
    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{_EXPORT_MODULES[name]}"), name)
    globals()[name] = value
    return value
