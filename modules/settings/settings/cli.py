"""CLI entry points for the Settings module.

Exposes ``sm-settings`` via ``[project.scripts]`` in ``pyproject.toml``.
Subcommand ``import-from-env`` walks the per-module ``BaseSettings``
classes on ``app.state.settings.module_registry`` and, for every field
whose ``SM_<PREFIX>_<FIELD>`` env var is set, writes a SYSTEM-scoped
override into the Settings store. This is a one-shot migration tool:
Phase 3 stripped ``env_prefix`` from module settings, so env-var names
can't be discovered from the pydantic config; we carry a small
package → prefix map for modules whose prefix doesn't follow the default
``SM_<PACKAGE_UPPER>_`` convention.
"""

from __future__ import annotations

import asyncio
import os
import sys

from fastapi import FastAPI

from settings.constants import MODULE_PACKAGE
from settings.hydrate import value_type_for_field
from settings.store import SettingsStore

# Modules whose historical env prefix doesn't match ``SM_<PACKAGE_UPPER>_``.
# Phase 3 removed ``env_prefix`` from pydantic configs, so the mapping has
# to live here for the one-shot import to land env vars on the right fields.
_PACKAGE_ENV_PREFIX: dict[str, str] = {
    "background_tasks": "SM_BG_TASKS_",
    "file_storage": "SM_FILE_STORAGE_",
}


def _env_prefix_for(package: str) -> str:
    return _PACKAGE_ENV_PREFIX.get(package, f"SM_{package.upper()}_")


async def import_from_env_impl(app: FastAPI, store: SettingsStore) -> int:
    """Write a SYSTEM override for every ``SM_<PREFIX>_<FIELD>`` env var set.

    Returns the count of overrides written. Unknown env vars (no matching
    field on any registered module) are ignored.
    """
    registry = getattr(app.state, MODULE_PACKAGE).module_registry
    count = 0
    for package, cls in registry.items():
        prefix = _env_prefix_for(package)
        for field_name in cls.model_fields:
            env_name = f"{prefix}{field_name.upper()}"
            raw = os.environ.get(env_name)
            if raw is None:
                continue
            vtype = value_type_for_field(cls, field_name)
            await store.set_override(package, field_name, raw, vtype)
            count += 1
    return count


def main() -> int:
    """Console-script entry point for ``sm-settings``.

    Supports a single subcommand: ``import-from-env``.
    """
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("Usage: sm-settings import-from-env")
        return 0 if argv else 1
    if argv[0] != "import-from-env":
        print(f"Unknown command: {argv[0]}", file=sys.stderr)
        print("Usage: sm-settings import-from-env", file=sys.stderr)
        return 2

    from simple_module_hosting.app_builder import create_app
    from simple_module_hosting.settings import Settings

    from settings.service import SettingService

    app = create_app(Settings())

    async def run() -> int:
        async with (
            app.router.lifespan_context(app),
            app.state.sm.db.session_factory() as session,
        ):
            store = SettingsStore(SettingService(session))
            n = await import_from_env_impl(app, store)
            await session.commit()
            print(f"Imported {n} override(s) from environment.")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
