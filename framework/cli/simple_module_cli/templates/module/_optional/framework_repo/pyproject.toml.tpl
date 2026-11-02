[project]
name = "simple_module_{{PACKAGE_NAME}}"
version = "0.1.0"
description = "The {{MODULE_NAME}} module"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "{{PACKAGE_NAME}}"]
dependencies = [
    "simple_module_core",
    "simple_module_db",
    "simple_module_hosting",
]

[project.entry-points.simple_module]
{{PACKAGE_NAME}} = "{{PACKAGE_NAME}}.module:{{MODULE_NAME}}Module"

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# The distribution name (simple_module_{{PACKAGE_NAME}}) doesn't match the package
# directory ({{PACKAGE_NAME}}), so hatchling can't infer what to ship — without
# this the wheel builds empty and the entry point fails to import.
[tool.hatch.build.targets.wheel]
packages = ["{{PACKAGE_NAME}}"]

# Ship the module-root package.json inside the wheel so the host can
# discover JS deps via importlib.resources after a pip install.
[tool.hatch.build.targets.wheel.force-include]
"package.json" = "{{PACKAGE_NAME}}/package.json"

[tool.uv.sources]
simple_module_core = { workspace = true }
simple_module_db = { workspace = true }
simple_module_hosting = { workspace = true }
