"""Site Lock module — optional site-wide password gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.module_settings import register_module_settings
from simple_module_hosting.session import preserve_across_sign_in

from site_lock import constants as c

if TYPE_CHECKING:
    from fastapi import FastAPI


class SiteLockModule(ModuleBase):
    meta = ModuleMeta(
        name=c.MODULE_NAME,
        # ``Settings`` keeps the module order unchanged (registering settings
        # no longer needs it, #500); ``Auth`` so this module sorts *after* auth and its
        # middleware therefore wraps outermost, executing before
        # AuthMiddleware. Both are load-bearing — see the module README.
        depends_on=[c.MODULE_AUTH],
        optional_depends_on=[c.MODULE_SETTINGS],
    )

    def register_settings(self, app: FastAPI) -> None:
        from site_lock.settings import SiteLockSettings
        from site_lock.state import SiteLockState

        # Signing in replaces the session; the unlock marker must outlive it.
        preserve_across_sign_in(app, c.SESSION_KEY)
        register_module_settings(
            app,
            c.MODULE_PACKAGE,
            SiteLockSettings,
            lambda s: SiteLockState(settings=s),
        )

    def register_middleware(self, app: FastAPI) -> None:
        from site_lock.middleware import SiteLockMiddleware

        app.add_middleware(SiteLockMiddleware)
