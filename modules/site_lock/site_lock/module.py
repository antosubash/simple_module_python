"""Site Lock module — optional site-wide password gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core.module import ModuleBase, ModuleMeta

from site_lock import constants as c

if TYPE_CHECKING:
    from fastapi import FastAPI


class SiteLockModule(ModuleBase):
    meta = ModuleMeta(
        name=c.MODULE_NAME,
        # ``Settings`` so register_module_settings can reach the module
        # registry; ``Auth`` so this module sorts *after* auth and its
        # middleware therefore wraps outermost, executing before
        # AuthMiddleware. Both are load-bearing — see the module README.
        depends_on=[c.MODULE_SETTINGS, c.MODULE_AUTH],
    )

    def register_settings(self, app: FastAPI) -> None:
        import importlib

        from site_lock.settings import SiteLockSettings
        from site_lock.state import SiteLockState

        # SM009 is AST-based: resolving via importlib matches the convention
        # used by the other settings-backed modules.
        register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings

        register_module_settings(
            app,
            c.MODULE_PACKAGE,
            SiteLockSettings,
            lambda s: SiteLockState(settings=s),
        )

    def register_middleware(self, app: FastAPI) -> None:
        from site_lock.middleware import SiteLockMiddleware

        app.add_middleware(SiteLockMiddleware)
