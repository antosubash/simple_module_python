"""Auth module — shared contracts (UserContext, deps).

Intentionally minimal: this module owns the PUBLIC interface (UserContext,
PrincipalResolver, get_current_user, CurrentUser, require_permission) that
every other module imports. Keeping it stable prevents churn when auth
internals change.

All authentication logic (middleware, login, signup, OAuth) lives in the
users module. The ``principal_resolvers`` registry on ``app.state.auth`` is
the extension point downstream modules use to plug in additional credential
sources (PAT bearer tokens, API keys, etc.) — see
``docs/framework/principal-resolvers.md`` for the worked example.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.module import ModuleBase, ModuleMeta

if TYPE_CHECKING:
    from fastapi import FastAPI


class AuthModule(ModuleBase):
    meta = ModuleMeta(
        name="Auth",
        route_prefix="/auth",
    )

    def register_settings(self, app: FastAPI) -> None:
        from auth.state import AuthState

        app.state.auth = AuthState()

    def locale_dirs(self) -> dict[str, Path]:
        return {"auth": Path(str(importlib.resources.files(__package__) / "locales"))}
