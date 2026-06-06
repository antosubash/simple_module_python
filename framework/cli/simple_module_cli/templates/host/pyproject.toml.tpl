[project]
name = "{{HOST_PYPI_NAME}}"
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

# Quality-gate config for `make test` / `make lint`. In a workspace scaffold
# the same config also lives at the workspace root (where those targets run);
# in a flat scaffold this host dir *is* the project root.
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
