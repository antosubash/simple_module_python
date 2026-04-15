[project]
name = "simple-module-{{MODULE_SLUG}}"
version = "0.1.0"
description = "{{MODULE_NAME}} module for SimpleModule hosts"
requires-python = ">=3.12"
dependencies = [
    "simple-module-core>=1.0,<2.0",
    "simple-module-db>=1.0,<2.0",
    "simple-module-hosting>=1.0,<2.0",
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
    "simple-module-testing>=0.1,<1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["{{PACKAGE_NAME}}"]

# Ship the built frontend bundle + per-module JS dep manifest inside the wheel.
# static/dist/ is gitignored, so force-include picks up the working-tree build
# during `uv build` — run your bundler (vite/esbuild) first. package.json lives
# at the module root so npm workspaces see it; copying it into <pkg>/ lets the
# host discover JS deps via importlib.resources after a pip install.
[tool.hatch.build.targets.wheel.force-include]
"{{PACKAGE_NAME}}/static/dist" = "{{PACKAGE_NAME}}/static/dist"
"package.json" = "{{PACKAGE_NAME}}/package.json"
