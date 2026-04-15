"""Auth module — shared contracts (UserContext, deps).

Intentionally minimal: this module owns the PUBLIC interface (UserContext,
get_current_user, CurrentUser, require_permission) that every other module
imports. Keeping it stable prevents churn when auth internals change.

All authentication logic (middleware, login, signup, OAuth) lives in the
users module.
"""

from __future__ import annotations

from simple_module_core.module import ModuleBase, ModuleMeta


class AuthModule(ModuleBase):
    meta = ModuleMeta(
        name="Auth",
        route_prefix="/auth",
    )
