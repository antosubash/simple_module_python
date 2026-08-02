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
        name = "simple_module_{ctx.pkg}"
        version = "0.1.0"
        description = "The {ctx.class_name} module"
        authors = []
        requires-python = ">=3.12"
        dependencies = [
            "simple_module_core",
            "simple_module_db",
            "simple_module_hosting",
        ]

        [project.entry-points.simple_module]
        {ctx.name} = "{ctx.pkg}.module:{ctx.class_name}Module"

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        # The distribution name (simple_module_{ctx.pkg}) doesn't match the package
        # directory ({ctx.pkg}), so hatchling can't infer what to ship — without
        # this the wheel builds empty and the entry point fails to import.
        [tool.hatch.build.targets.wheel]
        packages = ["{ctx.pkg}"]

        # Ship the module-root package.json inside the wheel so the host can
        # discover JS deps via importlib.resources after a pip install.
        [tool.hatch.build.targets.wheel.force-include]
        "package.json" = "{ctx.pkg}/package.json"

        [tool.uv.sources]
        simple_module_core = {{ workspace = true }}
        simple_module_db = {{ workspace = true }}
        simple_module_hosting = {{ workspace = true }}
        """


def package_init(ctx: ScaffoldContext) -> str:
    return f'''\
        """{ctx.class_name} module."""
        '''


def locales_en_json(ctx: ScaffoldContext) -> str:
    """Default English locale file for a scaffolded module.

    Keys here must stay in sync with the strings emitted by
    :func:`_templates_tsx.browse_tsx` / ``create_tsx`` / ``edit_tsx``.
    """
    return (
        "{\n"
        '  "browse": {\n'
        f'    "title": "{ctx.class_name}",\n'
        f'    "description": "Manage your {ctx.name}",\n'
        f'    "new_button": "New {ctx.singular_class}",\n'
        f'    "empty_title": "No {ctx.name} yet",\n'
        f'    "empty_description": "Get started by creating your first {ctx.singular}.",\n'
        '    "edit_link": "Edit"\n'
        "  },\n"
        '  "form": {\n'
        '    "name_label": "Name",\n'
        '    "description_label": "Description"\n'
        "  },\n"
        '  "create": {\n'
        f'    "title": "New {ctx.singular_class}",\n'
        f'    "submit_button": "Create"\n'
        "  },\n"
        '  "edit": {\n'
        f'    "title": "Edit {ctx.singular_class}",\n'
        '    "submit_button": "Save"\n'
        "  }\n"
        "}\n"
    )


def models_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """SQLModel tables for the {ctx.class_name} module."""

        from __future__ import annotations

        from simple_module_db.base import create_module_base
        from simple_module_db.mixins import AuditMixin
        from sqlmodel import Field

        # All modules share the host's single schema, so __tablename__ is
        # prefixed with the module name to avoid collisions.
        Base = create_module_base("{ctx.name}")


        class {ctx.singular_class}(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
            """A {ctx.singular} entity."""

            __tablename__ = "{ctx.name}_{ctx.singular}"

            id: int | None = Field(default=None, primary_key=True)
            name: str = Field(max_length=200)
            description: str | None = Field(default=None, max_length=2000)
            is_active: bool = Field(default=True)
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
