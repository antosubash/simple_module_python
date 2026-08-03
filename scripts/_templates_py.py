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
        readme = "README.md"
        license = "MIT"
        license-files = ["LICENSE"]
        requires-python = ">=3.12"
        authors = [{{ name = "Anto Subash", email = "antosubash@live.com" }}]
        keywords = ["simple-module", "{ctx.name}"]
        dependencies = [
            "simple_module_core",
            "simple_module_db",
            "simple_module_hosting",
        ]

        [project.entry-points.simple_module]
        {ctx.name} = "{ctx.pkg}.module:{ctx.class_name}Module"

        [project.urls]
        Homepage = "https://github.com/antosubash/simple_module_python"
        Repository = "https://github.com/antosubash/simple_module_python"
        Issues = "https://github.com/antosubash/simple_module_python/issues"
        Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

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


def readme_md(ctx: ScaffoldContext) -> str:
    """A README that satisfies scripts/check_readmes.py out of the box.

    That checker requires an H1, an "Install" and a "Usage" section, and at
    least 500 bytes — a scaffolded module used to fail `make lint` on all
    three until an author wrote one by hand.
    """
    return f"""\
        # simple_module_{ctx.pkg}

        The {ctx.class_name} module for
        [simple_module](https://github.com/antosubash/simple_module_python) apps.

        Replace this paragraph with a description of what the module actually does —
        the problem it solves and the surface it exposes to a host application.

        ## Install

        ```bash
        pip install simple_module_{ctx.pkg}
        ```

        Add `simple_module_{ctx.pkg}` to your host's dependencies; the
        `[project.entry-points.simple_module]` entry point is discovered automatically
        at boot, so no further wiring is required.

        ## Usage

        | Route | Page | Purpose |
        |---|---|---|
        | `GET /{ctx.name}/` | `{ctx.class_name}/Browse` | List view |
        | `GET /api/{ctx.name}/` | — | JSON list endpoint |

        Both are gated by the `{ctx.name}.view` permission. Document the real routes,
        settings (`SM_{ctx.name.upper()}_*`) and any events the module emits here.

        ## Configuration

        Settings live on `app.state.{ctx.pkg}` and use the `SM_{ctx.name.upper()}_*`
        environment prefix.
        """


def license_txt(ctx: ScaffoldContext) -> str:
    """MIT license — scripts/check_metadata.py requires license = "MIT"."""
    return """\
        MIT License

        Permission is hereby granted, free of charge, to any person obtaining a copy
        of this software and associated documentation files (the "Software"), to deal
        in the Software without restriction, including without limitation the rights
        to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
        copies of the Software, and to permit persons to whom the Software is
        furnished to do so, subject to the following conditions:

        The above copyright notice and this permission notice shall be included in all
        copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
        IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
        FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
        AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
        LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
        OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
        SOFTWARE.
        """
