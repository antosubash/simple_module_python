"""Template generators for a scaffolded module's definition layer.

Covers the three files that describe the module itself — its ``ModuleBase``
subclass, its settings, and its ``app.state`` container. Split out of
``_templates_py`` (which keeps the package/data-layer templates) to stay
under the repo's 300-line file cap.
"""

from __future__ import annotations

from _templates_py import ScaffoldContext


def module_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """{ctx.class_name} module definition."""

        from __future__ import annotations

        import importlib.resources
        from pathlib import Path

        from fastapi import APIRouter, FastAPI
        from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
        from simple_module_core.module import ModuleBase, ModuleMeta
        from simple_module_core.permissions import PermissionRegistry


        class {ctx.class_name}Module(ModuleBase):
            meta = ModuleMeta(
                name="{ctx.class_name}",
                route_prefix="/api/{ctx.name}",
                view_prefix="/{ctx.name}",
            )

            def register_settings(self, app: FastAPI) -> None:
                from {ctx.pkg}.services import {ctx.class_name}Services
                from {ctx.pkg}.settings import {ctx.class_name}Settings

                app.state.{ctx.pkg} = {ctx.class_name}Services(settings={ctx.class_name}Settings())

            def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
                from {ctx.pkg}.endpoints.api import router as api
                from {ctx.pkg}.endpoints.views import router as views

                api_router.include_router(api)
                view_router.include_router(views)

            def register_menu_items(self, registry: MenuRegistry) -> None:
                registry.add(
                    MenuItem(
                        label="{ctx.class_name}",
                        url="/{ctx.name}",
                        icon="box",
                        order=30,
                        section=MenuSection.SIDEBAR,
                        group="Content",
                    )
                )

            def register_permissions(self, registry: PermissionRegistry) -> None:
                registry.add_group(
                    "{ctx.class_name}",
                    [
                        "{ctx.name}.view",
                        "{ctx.name}.create",
                        "{ctx.name}.edit",
                        "{ctx.name}.delete",
                    ],
                )

            def locale_dirs(self) -> dict[str, Path]:
                base = Path(str(importlib.resources.files(__package__) / "locales"))
                return {{"{ctx.pkg}": base}}
        '''


def settings_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """{ctx.class_name} module settings (DB-backed).

        Values come from the pydantic defaults below at boot, then get hydrated
        from the settings store by the hosting lifespan before module
        ``on_startup`` runs. Runtime changes go through
        ``settings.reload.apply_changes_and_reload``.

        Add fields as the module needs them; an empty settings class is fine
        until then. ``extra="ignore"`` keeps an unknown stored key from
        breaking boot after a field is removed.
        """

        from __future__ import annotations

        from pydantic_settings import BaseSettings, SettingsConfigDict


        class {ctx.class_name}Settings(BaseSettings):
            """Configuration for the {ctx.pkg} module."""

            model_config = SettingsConfigDict(extra="ignore")

            enabled: bool = True
        '''


def services_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """Module-scoped state container.

        Stored as ``app.state.{ctx.pkg}`` by
        :meth:`{ctx.class_name}Module.register_settings`.

        Not frozen — ``on_startup`` may set fields that depend on the DB or
        other framework services. Convention: set once during boot, treat as
        read-only after.
        """

        from __future__ import annotations

        from dataclasses import dataclass

        from {ctx.pkg}.settings import {ctx.class_name}Settings


        @dataclass
        class {ctx.class_name}Services:
            """{ctx.class_name} module singletons."""

            settings: {ctx.class_name}Settings
        '''
