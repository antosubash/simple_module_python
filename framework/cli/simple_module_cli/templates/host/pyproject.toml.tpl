[project]
name = "{{HOST_NAME}}"
version = "0.1.0"
description = "SimpleModule host application"
requires-python = ">=3.12"
dependencies = [
    "simple_module_core>=1.0,<2.0",
    "simple_module_db>=1.0,<2.0",
    "simple_module_hosting>=1.0,<2.0",
    "simple_module_settings>=1.0,<2.0",
    "alembic>=1.13",
    "uvicorn[standard]>=0.34",
{{MODULE_DEPS}}
]

# Host is an application, not a distributable package.
[tool.uv]
package = false

# Workspace plumbing — local modules under modules/<name>/ are picked up
# automatically. Add a new module with `sm create-module <name>` (writes to
# modules/<name>/), then add `simple_module_<name>` to the dependency list
# above. uv resolves it from the workspace instead of PyPI.
[tool.uv.workspace]
members = ["modules/*"]
