"""SimpleModule Hosting - App builder, module loader, middleware pipeline."""

from simple_module_hosting._preapp_config import merge_host_settings
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.logging import correlation_id, setup_logging
from simple_module_hosting.settings import Settings
from simple_module_hosting.shared_props import (
    SharedPropsProvider,
    register_inertia_shared_provider,
)

__all__ = [
    "Settings",
    "SharedPropsProvider",
    "correlation_id",
    "create_app",
    "merge_host_settings",
    "register_inertia_shared_provider",
    "setup_logging",
]
