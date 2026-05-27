"""Auth module — shared contracts (UserContext, AuthProvider, deps).

Intentionally minimal: this module owns the PUBLIC interface (UserContext,
AuthProvider, PrincipalResolver, get_current_user, CurrentUser, require_permission)
that every other module imports. Keeping it stable prevents churn when auth
internals change.

The ``auth_provider`` slot on ``app.state.auth`` is the extension point
auth-provider modules (``users``, ``keycloak``) use to register themselves.
The ``principal_resolvers`` registry lets downstream modules add extra
credential sources (PAT bearer tokens, API keys, etc.).
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.module import ModuleBase, ModuleMeta

if TYPE_CHECKING:
    from fastapi import FastAPI

    from auth.contracts.schemas import UserContext


def _serialize_principal(user: UserContext) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "roles": user.roles,
    }


class AuthModule(ModuleBase):
    meta = ModuleMeta(
        name="Auth",
        route_prefix="/auth",
    )

    def register_settings(self, app: FastAPI) -> None:
        from auth.state import AuthState

        app.state.auth = AuthState()
        app.state.principal_serializer = _serialize_principal

    def register_middleware(self, app: FastAPI) -> None:
        from auth.middleware import AuthMiddleware

        app.add_middleware(AuthMiddleware)

    def locale_dirs(self) -> dict[str, Path]:
        return {"auth": Path(str(importlib.resources.files(__package__) / "locales"))}
