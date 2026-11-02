"""Dependency pins, ``.env`` DB URLs and ``pyproject.toml`` rewriting for ``smpy new``."""

from __future__ import annotations

from collections.abc import Sequence

from simple_module_cli.scaffolding import resolve_framework_version

_FRAMEWORK_VERSION = resolve_framework_version()

# Pin ``simple_module_cli`` as a dev dep so ``uv run smpy`` resolves to the
# project venv. The global ``uv tool`` install runs in its own isolated venv
# that can't see the project's plugin entry points (issue #134). The lint /
# test tooling (ruff, ty, pytest-*) backs the generated `make lint`/`make
# test` targets so a fresh app can run its own quality gates.
_APP_PY_DEV_DEPS = [
    f"simple_module_test=={_FRAMEWORK_VERSION}",
    f"simple_module_cli=={_FRAMEWORK_VERSION}",
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-playwright>=0.7.2",
    # Floor: unpinned, uv backtracks playwright to 1.18 (GH #445).
    "playwright>=1.45",
    "ruff>=0.8",
    "ty>=0.0.29",
]

_APP_NPM_DEPS = {
    "@simple-module-py/ui": _FRAMEWORK_VERSION,
    "@simple-module-py/i18n": _FRAMEWORK_VERSION,
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@inertiajs/react": "^3.7.0",
}
# Flat mode has no npm workspaces, so `client_app/package.json` is never
# installed — the root package.json seeded from these two dicts is the only
# manifest npm reads. It must therefore cover everything client_app needs to
# build, not just the framework pins: `vite.config.ts` imports
# `@tailwindcss/vite`, and `tsc` needs the @types packages. Keep this in step
# with templates/host/client_app/package.json.tpl.
_APP_NPM_DEV_DEPS = {
    "@simple-module-py/tsconfig": _FRAMEWORK_VERSION,
    "@tailwindcss/vite": "^4.0.0",
    "@types/node": "^26.5.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^6.1.1",
    "tailwindcss": "^4.0.0",
    "typescript": "^7.0.2",
    "vite": "^8.2.2",
}


def _db_url(db: str, db_name: str, *, flat: bool, password: str = "<POSTGRES_PASSWORD>") -> str:
    if db == "postgres":
        return f"postgresql+asyncpg://postgres:{password}@localhost:5432/{db_name}"
    # Workspace mode keeps the SQLite file next to host/'s alembic.ini so
    # `cd host && uvicorn` and `cd host && alembic` resolve the same path.
    return "sqlite+aiosqlite:///./app.db" if flat else "sqlite+aiosqlite:///./host/app.db"


def _rewrite_pyproject(
    text: str,
    deps: list[str],
    dev_deps: list[str],
    *,
    sources: Sequence[str] = (),
    project_name: str | None = None,
) -> str:
    """Replace deps in a host ``pyproject.toml`` and pin workspace sources.

    ``sources`` lists ``simple_module_*`` packages that should resolve from
    the uv workspace (``modules/*``) instead of PyPI. Emits a
    ``[tool.uv.sources]`` block per entry. Empty in flat mode.

    ``project_name`` overrides ``[project].name`` — set in workspace mode
    so the host's package name differs from the workspace root's.
    """
    import tomlkit

    doc = tomlkit.parse(text)
    project = doc.setdefault("project", tomlkit.table())
    if project_name is not None:
        project["name"] = project_name
    project["dependencies"] = list(deps)
    groups = doc.setdefault("dependency-groups", tomlkit.table())
    groups["dev"] = list(dev_deps)
    if sources:
        tool = doc.setdefault("tool", tomlkit.table())
        uv_table = tool.setdefault("uv", tomlkit.table())
        uv_sources = uv_table.setdefault("sources", tomlkit.table())
        for src in sources:
            uv_sources[src] = {"workspace": True}
    return tomlkit.dumps(doc)
