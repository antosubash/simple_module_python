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

# Dev tooling for `make test` / `make lint`. These live in the workspace
# root's dependency-group (synced by default by `uv sync --all-packages`)
# so the shared venv that `make test`/`lint`/`doctor` run against has them.
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-playwright>=0.7.2",
    "ruff>=0.8",
    "ty>=0.0.29",
    # Provides the build_test_app / fake_event_bus fixtures (pytest11 plugin).
    "simple_module_test=={{FRAMEWORK_VERSION}}",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "e2e: end-to-end tests requiring a live browser",
]
addopts = "-m 'not e2e'"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "SIM", "C4", "RET", "PTH", "PIE", "RUF"]
ignore = [
    "B008",  # Depends() in default args is idiomatic FastAPI
    "B027",  # Empty methods in ABC without @abstractmethod — used for optional hooks
]

# SQLModel declares fields with plain Python types even though at runtime they
# become SQLAlchemy InstrumentedAttributes (.in_(), .ilike(), ==, ...). ty can't
# see through this, so ORM query expressions trip these rules with false
# positives — real bugs still surface in tests.
[tool.ty.rules]
unresolved-attribute = "ignore"
unsupported-operator = "ignore"
unknown-argument = "ignore"
no-matching-overload = "ignore"
invalid-argument-type = "ignore"
invalid-assignment = "ignore"
