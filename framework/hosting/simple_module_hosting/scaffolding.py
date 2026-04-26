"""Re-exports of moved scaffolding APIs.

The actual implementations live in :mod:`simple_module.scaffolding`. This
shim lets the in-tree hosting code keep importing from the historical
path during the migration; it is removed in the final cleanup task.
"""

from __future__ import annotations

from simple_module.scaffolding import create_host, create_module

from simple_module_hosting.app_project import create_app_project as create_app_project
from simple_module_hosting.manifest import (
    collect_module_js_deps,
    compute_module_pages,
    read_module_package_json,
    repo_root_from_client_app,
    write_module_pages_manifest,
)

__all__ = [
    "collect_module_js_deps",
    "compute_module_pages",
    "create_app_project",
    "create_host",
    "create_module",
    "read_module_package_json",
    "repo_root_from_client_app",
    "write_module_pages_manifest",
]
