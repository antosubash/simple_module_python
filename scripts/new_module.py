#!/usr/bin/env python3
"""Scaffold a new module for the Simple Module Python framework.

Usage:
    python scripts/new_module.py <module_name>
    make new-module name=<module_name>

Creates the full module directory structure under modules/<name>/ with all
required files (pyproject.toml, module class, models, service, schemas,
endpoints, tests) and registers the module in host/pyproject.toml and
the root pyproject.toml.
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def validate_name(name: str) -> str:
    """Validate module name: lowercase, alphanumeric, underscores allowed."""
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        print(
            f"Error: Module name '{name}' is invalid. "
            "Use lowercase letters, digits, and underscores. Must start with a letter.",
            file=sys.stderr,
        )
        sys.exit(1)
    return name


def to_class_name(name: str) -> str:
    """Convert snake_case module name to PascalCase class name."""
    return "".join(word.capitalize() for word in name.split("_"))


def to_singular(name: str) -> str:
    """Naive singularization: strip trailing 's' if present."""
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def create_file(path: Path, content: str) -> None:
    """Create a file with the given content, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"))
    print(f"  created {path.relative_to(ROOT)}")


def scaffold_module(name: str) -> None:
    """Generate all files for a new module."""
    module_dir = ROOT / "modules" / name
    if module_dir.exists():
        print(f"Error: Module directory modules/{name}/ already exists.", file=sys.stderr)
        sys.exit(1)

    class_name = to_class_name(name)
    singular = to_singular(name)
    singular_class = to_class_name(singular)
    pkg = f"sm_{name}"
    src_dir = module_dir / pkg

    print(f"Scaffolding module '{name}'...")

    # ── pyproject.toml ──────────────────────────────────────────
    create_file(
        module_dir / "pyproject.toml",
        f"""\
        [project]
        name = "{pkg.replace('_', '-')}"
        version = "0.1.0"
        description = "The {class_name} module"
        authors = []
        requires-python = ">=3.12"
        dependencies = [
            "simple-module-core",
            "simple-module-db",
            "simple-module-hosting",
        ]

        [project.entry-points.simple_module]
        {name} = "{pkg}.module:{class_name}Module"

        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [tool.uv.sources]
        simple-module-core = {{ workspace = true }}
        simple-module-db = {{ workspace = true }}
        simple-module-hosting = {{ workspace = true }}
        """,
    )

    # ── __init__.py ─────────────────────────────────────────────
    create_file(
        src_dir / "__init__.py",
        f"""\
        \"""{class_name} module.\"""
        """,
    )

    # ── py.typed ────────────────────────────────────────────────
    create_file(src_dir / "py.typed", "")

    # ── module.py ───────────────────────────────────────────────
    create_file(
        src_dir / "module.py",
        f"""\
        \"""{class_name} module definition.\"""

        from __future__ import annotations

        from fastapi import APIRouter
        from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
        from simple_module_core.module import ModuleBase, ModuleMeta
        from simple_module_core.permissions import PermissionRegistry


        class {class_name}Module(ModuleBase):
            meta = ModuleMeta(
                name="{class_name}",
                route_prefix="/api/{name}",
                view_prefix="/{name}",
            )

            def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
                from {pkg}.endpoints.api import router as api
                from {pkg}.endpoints.views import router as views

                api_router.include_router(api)
                view_router.include_router(views)

            def register_menu_items(self, registry: MenuRegistry) -> None:
                registry.add(
                    MenuItem(
                        label="{class_name}",
                        url="/{name}",
                        icon="box",
                        order=30,
                        section=MenuSection.SIDEBAR,
                    )
                )

            def register_permissions(self, registry: PermissionRegistry) -> None:
                registry.add_group(
                    "{class_name}",
                    [
                        "{name}.view",
                        "{name}.create",
                        "{name}.edit",
                        "{name}.delete",
                    ],
                )
        """,
    )

    # ── models.py ───────────────────────────────────────────────
    create_file(
        src_dir / "models.py",
        f"""\
        \"""SQLAlchemy models for the {class_name} module.\"""

        from __future__ import annotations

        from simple_module_db.base import create_module_base
        from simple_module_db.mixins import AuditMixin
        from simple_module_db.provider import DatabaseProvider
        from sqlalchemy import String
        from sqlalchemy.orm import Mapped, mapped_column

        Base = create_module_base("{name}", provider=DatabaseProvider.SQLITE)


        class {singular_class}(Base, AuditMixin):  # ty: ignore[unsupported-base]
            \"""A {singular} entity.\"""

            __tablename__ = "{name}_{singular}"

            id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
            name: Mapped[str] = mapped_column(String(200))
            description: Mapped[str | None] = mapped_column(String(2000), default=None)
            is_active: Mapped[bool] = mapped_column(default=True)
        """,
    )

    # ── contracts/__init__.py ───────────────────────────────────
    create_file(
        src_dir / "contracts" / "__init__.py",
        f"""\
        \"""{class_name} contracts — public interface for other modules.\"""

        from {pkg}.contracts.schemas import (
            {singular_class}Create,
            {singular_class}Out,
            {singular_class}Update,
        )
        from {pkg}.contracts.service import I{singular_class}Service

        __all__ = [
            "{singular_class}Create",
            "{singular_class}Out",
            "{singular_class}Update",
            "I{singular_class}Service",
        ]
        """,
    )

    # ── contracts/schemas.py ────────────────────────────────────
    create_file(
        src_dir / "contracts" / "schemas.py",
        f"""\
        \"""Pydantic DTOs for the {class_name} module.\"""

        from __future__ import annotations

        from datetime import datetime

        from pydantic import BaseModel, ConfigDict, Field


        class {singular_class}Out(BaseModel):
            \"""{singular_class} data returned by the API.\"""

            model_config = ConfigDict(from_attributes=True)

            id: int
            name: str
            description: str | None = None
            is_active: bool
            created_at: datetime | None = None
            updated_at: datetime | None = None


        class {singular_class}Create(BaseModel):
            \"""Data required to create a new {singular}.\"""

            name: str = Field(min_length=1, max_length=200)
            description: str | None = None


        class {singular_class}Update(BaseModel):
            \"""Data to update an existing {singular}. All fields optional.\"""

            name: str | None = Field(default=None, min_length=1, max_length=200)
            description: str | None = None
            is_active: bool | None = None
        """,
    )

    # ── contracts/service.py ────────────────────────────────────
    create_file(
        src_dir / "contracts" / "service.py",
        f"""\
        \"""{singular_class} service protocol — the public contract other modules depend on.\"""

        from __future__ import annotations

        from typing import Protocol

        from {pkg}.contracts.schemas import (
            {singular_class}Create,
            {singular_class}Out,
            {singular_class}Update,
        )


        class I{singular_class}Service(Protocol):
            \"""Interface for {singular} operations.\"""

            async def get_all(self) -> list[{singular_class}Out]: ...
            async def get_by_id(self, {singular}_id: int) -> {singular_class}Out | None: ...
            async def create(self, data: {singular_class}Create) -> {singular_class}Out: ...
            async def update(
                self, {singular}_id: int, data: {singular_class}Update
            ) -> {singular_class}Out | None: ...
            async def delete(self, {singular}_id: int) -> bool: ...
        """,
    )

    # ── service.py ──────────────────────────────────────────────
    create_file(
        src_dir / "service.py",
        f"""\
        \"""{singular_class} service implementation.\"""

        from __future__ import annotations

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        from {pkg}.contracts.schemas import (
            {singular_class}Create,
            {singular_class}Out,
            {singular_class}Update,
        )
        from {pkg}.models import {singular_class}


        class {singular_class}Service:
            \"""CRUD operations for {name}.\"""

            def __init__(self, db: AsyncSession) -> None:
                self.db = db

            async def get_all(self) -> list[{singular_class}Out]:
                result = await self.db.execute(
                    select({singular_class})
                    .where({singular_class}.is_active.is_(True))
                    .order_by({singular_class}.id)
                )
                return [{singular_class}Out.model_validate(row) for row in result.scalars()]

            async def get_by_id(self, {singular}_id: int) -> {singular_class}Out | None:
                entity = await self.db.get({singular_class}, {singular}_id)
                if entity is None:
                    return None
                return {singular_class}Out.model_validate(entity)

            async def create(self, data: {singular_class}Create) -> {singular_class}Out:
                entity = {singular_class}(**data.model_dump())
                self.db.add(entity)
                await self.db.flush()
                await self.db.refresh(entity)
                return {singular_class}Out.model_validate(entity)

            async def update(
                self, {singular}_id: int, data: {singular_class}Update
            ) -> {singular_class}Out | None:
                entity = await self.db.get({singular_class}, {singular}_id)
                if entity is None:
                    return None
                for field, value in data.model_dump(exclude_unset=True).items():
                    setattr(entity, field, value)
                await self.db.flush()
                await self.db.refresh(entity)
                return {singular_class}Out.model_validate(entity)

            async def delete(self, {singular}_id: int) -> bool:
                entity = await self.db.get({singular_class}, {singular}_id)
                if entity is None:
                    return False
                await self.db.delete(entity)
                return True
        """,
    )

    # ── deps.py ─────────────────────────────────────────────────
    create_file(
        src_dir / "deps.py",
        f"""\
        \"""FastAPI dependencies for the {class_name} module.\"""

        from __future__ import annotations

        from fastapi import Depends
        from simple_module_db.deps import get_db
        from sqlalchemy.ext.asyncio import AsyncSession

        from {pkg}.service import {singular_class}Service


        async def get_{singular}_service(
            db: AsyncSession = Depends(get_db),
        ) -> {singular_class}Service:
            return {singular_class}Service(db)
        """,
    )

    # ── endpoints/__init__.py ───────────────────────────────────
    create_file(src_dir / "endpoints" / "__init__.py", "")

    # ── endpoints/api.py ────────────────────────────────────────
    create_file(
        src_dir / "endpoints" / "api.py",
        f"""\
        \"""REST API endpoints for {class_name}.\"""

        from __future__ import annotations

        from fastapi import APIRouter, Depends, HTTPException

        from {pkg}.contracts.schemas import (
            {singular_class}Create,
            {singular_class}Out,
            {singular_class}Update,
        )
        from {pkg}.deps import get_{singular}_service
        from {pkg}.service import {singular_class}Service

        router = APIRouter()


        @router.get("/", response_model=list[{singular_class}Out])
        async def list_{name}(
            service: {singular_class}Service = Depends(get_{singular}_service),
        ) -> list[{singular_class}Out]:
            return await service.get_all()


        @router.get("/{{{singular}_id}}", response_model={singular_class}Out)
        async def get_{singular}(
            {singular}_id: int,
            service: {singular_class}Service = Depends(get_{singular}_service),
        ) -> {singular_class}Out:
            result = await service.get_by_id({singular}_id)
            if result is None:
                raise HTTPException(status_code=404, detail="{singular_class} not found")
            return result


        @router.post("/", response_model={singular_class}Out, status_code=201)
        async def create_{singular}(
            data: {singular_class}Create,
            service: {singular_class}Service = Depends(get_{singular}_service),
        ) -> {singular_class}Out:
            return await service.create(data)


        @router.put("/{{{singular}_id}}", response_model={singular_class}Out)
        async def update_{singular}(
            {singular}_id: int,
            data: {singular_class}Update,
            service: {singular_class}Service = Depends(get_{singular}_service),
        ) -> {singular_class}Out:
            result = await service.update({singular}_id, data)
            if result is None:
                raise HTTPException(status_code=404, detail="{singular_class} not found")
            return result


        @router.delete("/{{{singular}_id}}", status_code=204)
        async def delete_{singular}(
            {singular}_id: int,
            service: {singular_class}Service = Depends(get_{singular}_service),
        ) -> None:
            deleted = await service.delete({singular}_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="{singular_class} not found")
        """,
    )

    # ── endpoints/views.py ──────────────────────────────────────
    create_file(
        src_dir / "endpoints" / "views.py",
        f"""\
        \"""Inertia view endpoints for {class_name}.\"""

        from __future__ import annotations

        from fastapi import APIRouter, Depends
        from inertia import InertiaResponse
        from simple_module_hosting.inertia_deps import InertiaDep

        from {pkg}.deps import get_{singular}_service
        from {pkg}.service import {singular_class}Service

        router = APIRouter()


        @router.get("/", response_model=None)
        async def browse(
            inertia: InertiaDep,
            service: {singular_class}Service = Depends(get_{singular}_service),
        ) -> InertiaResponse:
            items = await service.get_all()
            return await inertia.render(
                "{class_name}/Browse",
                {{"{name}": [item.model_dump(mode="json") for item in items]}},
            )


        @router.get("/create", response_model=None)
        async def create_view(inertia: InertiaDep) -> InertiaResponse:
            return await inertia.render("{class_name}/Create")


        @router.get("/{{{singular}_id}}/edit", response_model=None)
        async def edit_view(
            {singular}_id: int,
            inertia: InertiaDep,
            service: {singular_class}Service = Depends(get_{singular}_service),
        ) -> InertiaResponse:
            item = await service.get_by_id({singular}_id)
            if item is None:
                return await inertia.render(
                    "{class_name}/Browse",
                    {{"error": "{singular_class} not found"}},
                )
            return await inertia.render(
                "{class_name}/Edit",
                {{"{singular}": item.model_dump(mode="json")}},
            )
        """,
    )

    # ── tests/test_<name>.py ────────────────────────────────────
    create_file(
        module_dir / "tests" / f"test_{name}.py",
        f"""\
        \"""Tests for the {class_name} module: service CRUD, API endpoints, schema validation.\"""

        from __future__ import annotations

        import httpx
        import pytest
        from pydantic import ValidationError
        from {pkg}.contracts.schemas import {singular_class}Create, {singular_class}Update
        from {pkg}.service import {singular_class}Service
        from sqlalchemy.ext.asyncio import AsyncSession

        # ── Schema validation ────────────────────────────────────────────────


        class Test{singular_class}Schemas:
            async def test_create_valid(self):
                data = {singular_class}Create(name="Test {singular_class}")
                assert data.name == "Test {singular_class}"
                assert data.description is None

            async def test_create_empty_name_rejected(self):
                with pytest.raises(ValidationError):
                    {singular_class}Create(name="")

            async def test_update_all_optional(self):
                data = {singular_class}Update()
                assert data.name is None
                assert data.is_active is None


        # ── {singular_class}Service CRUD ──────────────────────────────────────────────


        class Test{singular_class}Service:
            async def test_create(self, db_session: AsyncSession):
                svc = {singular_class}Service(db_session)
                item = await svc.create({singular_class}Create(name="Test"))
                assert item.id is not None
                assert item.name == "Test"
                assert item.is_active is True

            async def test_get_all(self, db_session: AsyncSession):
                svc = {singular_class}Service(db_session)
                await svc.create({singular_class}Create(name="A"))
                await svc.create({singular_class}Create(name="B"))
                items = await svc.get_all()
                assert len(items) == 2

            async def test_get_by_id(self, db_session: AsyncSession):
                svc = {singular_class}Service(db_session)
                created = await svc.create({singular_class}Create(name="X"))
                found = await svc.get_by_id(created.id)
                assert found is not None
                assert found.name == "X"

            async def test_get_by_id_not_found(self, db_session: AsyncSession):
                svc = {singular_class}Service(db_session)
                found = await svc.get_by_id(999)
                assert found is None

            async def test_update(self, db_session: AsyncSession):
                svc = {singular_class}Service(db_session)
                created = await svc.create({singular_class}Create(name="Old"))
                updated = await svc.update(created.id, {singular_class}Update(name="New"))
                assert updated is not None
                assert updated.name == "New"

            async def test_update_not_found(self, db_session: AsyncSession):
                svc = {singular_class}Service(db_session)
                result = await svc.update(999, {singular_class}Update(name="Ghost"))
                assert result is None

            async def test_delete(self, db_session: AsyncSession):
                svc = {singular_class}Service(db_session)
                created = await svc.create({singular_class}Create(name="Doomed"))
                deleted = await svc.delete(created.id)
                assert deleted is True

            async def test_delete_not_found(self, db_session: AsyncSession):
                svc = {singular_class}Service(db_session)
                deleted = await svc.delete(999)
                assert deleted is False


        # ── API endpoints ───────────────────────────────────────────────


        class Test{class_name}API:
            async def test_list_empty(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.get("/api/{name}/")
                assert resp.status_code == 200
                assert resp.json() == []

            async def test_create(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.post(
                    "/api/{name}/",
                    json={{"name": "Test {singular_class}"}},
                )
                assert resp.status_code == 201
                data = resp.json()
                assert data["name"] == "Test {singular_class}"
                assert data["id"] is not None

            async def test_get_by_id(self, authenticated_client: httpx.AsyncClient):
                create_resp = await authenticated_client.post(
                    "/api/{name}/",
                    json={{"name": "Findable"}},
                )
                item_id = create_resp.json()["id"]
                resp = await authenticated_client.get(f"/api/{name}/{{item_id}}")
                assert resp.status_code == 200
                assert resp.json()["name"] == "Findable"

            async def test_get_not_found(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.get("/api/{name}/99999")
                assert resp.status_code == 404

            async def test_update(self, authenticated_client: httpx.AsyncClient):
                create_resp = await authenticated_client.post(
                    "/api/{name}/",
                    json={{"name": "Original"}},
                )
                item_id = create_resp.json()["id"]
                resp = await authenticated_client.put(
                    f"/api/{name}/{{item_id}}",
                    json={{"name": "Updated"}},
                )
                assert resp.status_code == 200
                assert resp.json()["name"] == "Updated"

            async def test_delete(self, authenticated_client: httpx.AsyncClient):
                create_resp = await authenticated_client.post(
                    "/api/{name}/",
                    json={{"name": "Deletable"}},
                )
                item_id = create_resp.json()["id"]
                resp = await authenticated_client.delete(f"/api/{name}/{{item_id}}")
                assert resp.status_code == 204

            async def test_delete_not_found(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.delete("/api/{name}/99999")
                assert resp.status_code == 404

            async def test_create_invalid_data(self, authenticated_client: httpx.AsyncClient):
                resp = await authenticated_client.post(
                    "/api/{name}/",
                    json={{"name": ""}},
                )
                assert resp.status_code == 422


        # ── Module lifecycle ────────────────────────────────────────────────


        class Test{class_name}ModuleLifecycle:
            async def test_on_startup_does_not_call_create_all(self):
                \"""on_startup should not create tables — Alembic manages schema.\"""
                from unittest.mock import AsyncMock, MagicMock

                from {pkg}.module import {class_name}Module

                mod = {class_name}Module()
                mock_app = MagicMock()
                mock_app.state.db.engine = AsyncMock()

                await mod.on_startup(mock_app)

                mock_app.state.db.engine.begin.assert_not_called()
        """,
    )


def _insert_after_last_match(content: str, pattern: str, line_to_insert: str) -> str | None:
    """Insert ``line_to_insert`` on a new line after the last line matching ``pattern``.

    Returns the modified content, or None if no line matched.
    """
    matches = list(re.finditer(pattern, content, re.MULTILINE))
    if not matches:
        return None
    last = matches[-1]
    end_of_line = content.find("\n", last.end())
    if end_of_line == -1:
        end_of_line = len(content)
    return content[: end_of_line + 1] + line_to_insert + content[end_of_line + 1 :]


def update_host_pyproject(name: str) -> None:
    """Add the new module as a dependency in host/pyproject.toml."""
    host_toml = ROOT / "host" / "pyproject.toml"
    content = host_toml.read_text()
    pkg = f"sm-{name.replace('_', '-')}"

    if pkg in content:
        print(f"  host/pyproject.toml already contains {pkg}, skipping")
        return

    original = content

    # Add to [project] dependencies — insert after last "sm-*" dep line
    result = _insert_after_last_match(
        content,
        r'^    "sm-[\w-]+",\s*$',
        f'    "{pkg}",\n',
    )
    if result:
        content = result

    # Add to [tool.uv.sources] — insert after last workspace source line
    result = _insert_after_last_match(
        content,
        r"^sm-[\w-]+ = \{ workspace = true \}\s*$",
        f"{pkg} = {{ workspace = true }}\n",
    )
    if result:
        content = result

    if content == original:
        print(
            f"  warning: could not find insertion point in host/pyproject.toml for {pkg}",
            file=sys.stderr,
        )
        return

    host_toml.write_text(content)
    print(f"  updated host/pyproject.toml (added {pkg})")


def update_root_pyproject(name: str) -> None:
    """Add the module to type-checking paths and test paths in root pyproject.toml."""
    root_toml = ROOT / "pyproject.toml"
    content = root_toml.read_text()
    src_path = f"modules/{name}"
    test_path = f"modules/{name}/tests"

    if f'"{src_path}",' in content and f'"{test_path}"' in content:
        print(f"  root pyproject.toml already contains modules/{name}, skipping")
        return

    original = content

    # Add to [tool.ty.environment] extra-paths — insert after last "modules/*" entry
    result = _insert_after_last_match(
        content,
        r'^    "modules/[\w/]+",\s*$',
        f'    "{src_path}",\n',
    )
    if result:
        content = result

    # Append after the last "modules/*/tests" entry, before the closing ]
    testpath_matches = list(re.finditer(r'"modules/[\w/]+/tests"', content))
    if testpath_matches and f'"{test_path}"' not in content:
        last = testpath_matches[-1]
        content = content[: last.end()] + f', "{test_path}"' + content[last.end() :]

    if content == original:
        print(
            "  warning: could not find insertion point in pyproject.toml",
            file=sys.stderr,
        )
        return

    root_toml.write_text(content)
    print("  updated pyproject.toml (added type-check path + test path)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scaffold a new module for Simple Module Python",
    )
    parser.add_argument(
        "name",
        help="Module name in snake_case (e.g. 'orders', 'blog_posts')",
    )
    args = parser.parse_args()

    name = validate_name(args.name)

    scaffold_module(name)
    update_host_pyproject(name)
    update_root_pyproject(name)

    print()
    print(f"Module '{name}' scaffolded successfully!")
    print()
    print("Next steps:")
    print("  1. Run 'uv sync --all-packages' to install the new module")
    print(f"  2. Edit modules/{name}/sm_{name}/models.py to define your domain model")
    print("  3. Update schemas, service, and endpoints to match your model")
    print(f'  4. Run \'make migration msg="add {name} tables"\' to create a migration')
    print("  5. Run 'make test' to verify everything works")


if __name__ == "__main__":
    main()
