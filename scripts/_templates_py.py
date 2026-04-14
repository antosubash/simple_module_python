"""Template generators for Python files scaffolded by new_module.

Each function returns the file content for a single generated Python file.
Context is passed via the ``ScaffoldContext`` dataclass so the signatures
stay compact.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScaffoldContext:
    """Naming variables for all generated templates."""

    name: str  # snake_case plural, e.g. "orders"
    class_name: str  # PascalCase plural, e.g. "Orders"
    singular: str  # snake_case singular, e.g. "order"
    singular_class: str  # PascalCase singular, e.g. "Order"
    pkg: str  # Python package name (same as name today)


def pyproject_toml(ctx: ScaffoldContext) -> str:
    return f"""\
        [project]
        name = "{ctx.pkg.replace("_", "-")}"
        version = "0.1.0"
        description = "The {ctx.class_name} module"
        authors = []
        requires-python = ">=3.12"
        dependencies = [
            "simple-module-core",
            "simple-module-db",
            "simple-module-hosting",
        ]

        [project.entry-points.simple_module]
        {ctx.name} = "{ctx.pkg}.module:{ctx.class_name}Module"

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [tool.uv.sources]
        simple-module-core = {{ workspace = true }}
        simple-module-db = {{ workspace = true }}
        simple-module-hosting = {{ workspace = true }}
        """


def package_init(ctx: ScaffoldContext) -> str:
    return f'''\
        """{ctx.class_name} module."""
        '''


def module_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """{ctx.class_name} module definition."""

        from __future__ import annotations

        from fastapi import APIRouter
        from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
        from simple_module_core.module import ModuleBase, ModuleMeta
        from simple_module_core.permissions import PermissionRegistry


        class {ctx.class_name}Module(ModuleBase):
            meta = ModuleMeta(
                name="{ctx.class_name}",
                route_prefix="/api/{ctx.name}",
                view_prefix="/{ctx.name}",
            )

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
        '''


def models_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """SQLAlchemy models for the {ctx.class_name} module."""

        from __future__ import annotations

        from simple_module_db.base import create_module_base
        from simple_module_db.mixins import AuditMixin
        from sqlalchemy import String
        from sqlalchemy.orm import Mapped, mapped_column

        # Provider is auto-detected from SM_DATABASE_URL (falls back to SQLite).
        # On PostgreSQL this gives the module its own `{ctx.name}` schema; on SQLite
        # all modules share one schema, so __tablename__ is prefixed for isolation.
        Base = create_module_base("{ctx.name}")


        class {ctx.singular_class}(Base, AuditMixin):  # ty: ignore[unsupported-base]
            """A {ctx.singular} entity."""

            __tablename__ = "{ctx.name}_{ctx.singular}"

            id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
            name: Mapped[str] = mapped_column(String(200))
            description: Mapped[str | None] = mapped_column(String(2000), default=None)
            is_active: Mapped[bool] = mapped_column(default=True)
        '''


def service_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """{ctx.singular_class} service implementation."""

        from __future__ import annotations

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        from {ctx.pkg}.contracts.schemas import (
            {ctx.singular_class}Create,
            {ctx.singular_class}Out,
            {ctx.singular_class}Update,
        )
        from {ctx.pkg}.models import {ctx.singular_class}


        class {ctx.singular_class}Service:
            """CRUD operations for {ctx.name}."""

            def __init__(self, db: AsyncSession) -> None:
                self.db = db

            async def get_all(self) -> list[{ctx.singular_class}Out]:
                result = await self.db.execute(
                    select({ctx.singular_class})
                    .where({ctx.singular_class}.is_active.is_(True))
                    .order_by({ctx.singular_class}.id)
                )
                return [{ctx.singular_class}Out.model_validate(row) for row in result.scalars()]

            async def get_by_id(self, {ctx.singular}_id: int) -> {ctx.singular_class}Out | None:
                entity = await self.db.get({ctx.singular_class}, {ctx.singular}_id)
                if entity is None:
                    return None
                return {ctx.singular_class}Out.model_validate(entity)

            async def create(self, data: {ctx.singular_class}Create) -> {ctx.singular_class}Out:
                entity = {ctx.singular_class}(**data.model_dump())
                self.db.add(entity)
                await self.db.flush()
                await self.db.refresh(entity)
                return {ctx.singular_class}Out.model_validate(entity)

            async def update(
                self, {ctx.singular}_id: int, data: {ctx.singular_class}Update
            ) -> {ctx.singular_class}Out | None:
                entity = await self.db.get({ctx.singular_class}, {ctx.singular}_id)
                if entity is None:
                    return None
                for field, value in data.model_dump(exclude_unset=True).items():
                    setattr(entity, field, value)
                await self.db.flush()
                await self.db.refresh(entity)
                return {ctx.singular_class}Out.model_validate(entity)

            async def delete(self, {ctx.singular}_id: int) -> bool:
                entity = await self.db.get({ctx.singular_class}, {ctx.singular}_id)
                if entity is None:
                    return False
                await self.db.delete(entity)
                return True
        '''


def deps_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """FastAPI dependencies for the {ctx.class_name} module."""

        from __future__ import annotations

        from fastapi import Depends
        from simple_module_db.deps import get_db
        from sqlalchemy.ext.asyncio import AsyncSession

        from {ctx.pkg}.service import {ctx.singular_class}Service


        async def get_{ctx.singular}_service(
            db: AsyncSession = Depends(get_db),
        ) -> {ctx.singular_class}Service:
            return {ctx.singular_class}Service(db)
        '''
