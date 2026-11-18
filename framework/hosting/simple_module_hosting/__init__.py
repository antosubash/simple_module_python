"""SimpleModule Hosting - App builder, module loader, middleware pipeline."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simple_module_hosting._preapp_config import merge_host_settings as merge_host_settings
    from simple_module_hosting.app_builder import create_app as create_app
    from simple_module_hosting.errors import render_error_page as render_error_page
    from simple_module_hosting.logging import correlation_id as correlation_id
    from simple_module_hosting.logging import setup_logging as setup_logging
    from simple_module_hosting.settings import Settings as Settings
    from simple_module_hosting.shared_props import SharedPropsProvider as SharedPropsProvider
    from simple_module_hosting.shared_props import (
        register_inertia_shared_provider as register_inertia_shared_provider,
    )
    from simple_module_hosting.shared_props import (
        replace_inertia_shared_prop as replace_inertia_shared_prop,
    )

__all__ = [
    "Settings",
    "SharedPropsProvider",
    "correlation_id",
    "create_app",
    "merge_host_settings",
    "register_inertia_shared_provider",
    "render_error_page",
    "replace_inertia_shared_prop",
    "setup_logging",
]

_EXPORT_MODULES = {
    "Settings": "settings",
    "SharedPropsProvider": "shared_props",
    "correlation_id": "logging",
    "create_app": "app_builder",
    "merge_host_settings": "_preapp_config",
    "register_inertia_shared_provider": "shared_props",
    "replace_inertia_shared_prop": "shared_props",
    "render_error_page": "errors",
    "setup_logging": "logging",
}


def __getattr__(name: str):
    # The host factory must load dotenv before importing settings or app_builder.
    if name not in _EXPORT_MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{_EXPORT_MODULES[name]}"), name)
    globals()[name] = value
    return value
