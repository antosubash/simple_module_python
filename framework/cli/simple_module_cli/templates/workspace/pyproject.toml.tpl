[project]
name = "{{HOST_PYPI_NAME}}"
version = "0.1.0"
description = "SimpleModule application workspace root"
requires-python = ">=3.12"
dependencies = []

# Workspace root: not built or installed itself.
[tool.uv]
package = false

# uv workspace — `host/` is the application; modules/* are workspace
# members so you can iterate on them without publishing to PyPI. Add a
# `[tool.uv.sources]` entry in host/pyproject.toml for each in-repo
# module: `simple_module_<name> = { workspace = true }`.
[tool.uv.workspace]
members = ["host", "modules/*"]
