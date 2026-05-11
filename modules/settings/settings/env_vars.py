"""Map package names to their historical ``SM_*`` env-var prefix.

Used by ``_module_settings`` to label fields in the admin UI and by the
``smpy settings import-from-env`` CLI to locate legacy env values. Most
packages follow ``SM_<PACKAGE_UPPER>_``; the exceptions are listed below.
"""

from __future__ import annotations

_PACKAGE_ENV_PREFIX: dict[str, str] = {
    "background_tasks": "SM_BG_TASKS_",
    "file_storage": "SM_FILE_STORAGE_",
    "host": "SM_",
}


def env_prefix_for(package: str) -> str:
    return _PACKAGE_ENV_PREFIX.get(package, f"SM_{package.upper()}_")
