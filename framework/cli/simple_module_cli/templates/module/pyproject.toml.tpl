[project]
name = "simple_module_{{PACKAGE_NAME}}"
version = "0.1.0"
description = "{{MODULE_NAME}} module for SimpleModule hosts"
requires-python = ">=3.12"
dependencies = [
    "simple_module_core>=1.0,<2.0",
    "simple_module_db>=1.0,<2.0",
    "simple_module_hosting>=1.0,<2.0",
    "pydantic-settings>=2.0",
    "sqlalchemy>=2.0",
]

[project.entry-points.simple_module]
{{PACKAGE_NAME}} = "{{PACKAGE_NAME}}.module:{{MODULE_NAME}}Module"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    # Shared fixtures (fake_event_bus, build_test_app, etc.) for testing
    # modules in isolation. The pytest11 entry_point auto-registers them.
    "simple_module_test>=0.1,<1.0",
    # `smpy module verify` / `smpy module build` for out-of-tree frontend work.
    "simple_module_cli>=0.1,<1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["{{PACKAGE_NAME}}"]
# Ship the built frontend bundle inside the wheel when present. static/dist/
# is gitignored, so it needs an explicit artifacts entry — run
# `smpy module build` before `uv build` to populate it. (artifacts, unlike
# force-include, tolerates the directory not existing yet, so a fresh
# scaffold/clone still `uv sync`s.)
artifacts = ["{{PACKAGE_NAME}}/static/dist/"]

# package.json lives at the module root so npm workspaces see it; copying it
# into <pkg>/ lets the host discover JS deps via importlib.resources after a
# pip install.
[tool.hatch.build.targets.wheel.force-include]
"package.json" = "{{PACKAGE_NAME}}/package.json"
