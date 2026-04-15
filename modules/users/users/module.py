"""Users module definition."""

from __future__ import annotations

from simple_module_core.module import ModuleBase, ModuleMeta


class UsersModule(ModuleBase):
    meta = ModuleMeta(
        name="Users",
        route_prefix="/api/users",
        view_prefix="/users",
        depends_on=["Auth"],
    )
