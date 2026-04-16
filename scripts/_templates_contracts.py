"""Template generators for the contracts/ sub-package (schemas + service protocol)."""

from __future__ import annotations

from _templates_py import ScaffoldContext


def contracts_init(ctx: ScaffoldContext) -> str:
    return f'''\
        """{ctx.class_name} contracts — public interface for other modules."""

        from {ctx.pkg}.contracts.schemas import (
            {ctx.singular_class}Create,
            {ctx.singular_class}Out,
            {ctx.singular_class}Update,
        )
        from {ctx.pkg}.contracts.service import I{ctx.singular_class}Service

        __all__ = [
            "{ctx.singular_class}Create",
            "{ctx.singular_class}Out",
            "{ctx.singular_class}Update",
            "I{ctx.singular_class}Service",
        ]
        '''


def schemas_py(ctx: ScaffoldContext) -> str:
    return f'''\
        """SQLModel DTOs for the {ctx.class_name} module."""

        from __future__ import annotations

        from datetime import datetime

        from pydantic import ConfigDict
        from sqlmodel import Field, SQLModel


        class {ctx.singular_class}Out(SQLModel):
            """{ctx.singular_class} data returned by the API."""

            model_config = ConfigDict(from_attributes=True)

            id: int
            name: str
            description: str | None = None
            is_active: bool
            created_at: datetime | None = None
            updated_at: datetime | None = None


        class {ctx.singular_class}Create(SQLModel):
            """Data required to create a new {ctx.singular}."""

            name: str = Field(min_length=1, max_length=200)
            description: str | None = None


        class {ctx.singular_class}Update(SQLModel):
            """Data to update an existing {ctx.singular}. All fields optional."""

            name: str | None = Field(default=None, min_length=1, max_length=200)
            description: str | None = None
            is_active: bool | None = None
        '''


def contracts_service(ctx: ScaffoldContext) -> str:
    return f'''\
        """{ctx.singular_class} service protocol — the public contract other modules depend on."""

        from __future__ import annotations

        from typing import Protocol

        from {ctx.pkg}.contracts.schemas import (
            {ctx.singular_class}Create,
            {ctx.singular_class}Out,
            {ctx.singular_class}Update,
        )


        class I{ctx.singular_class}Service(Protocol):
            """Interface for {ctx.singular} operations."""

            async def get_all(self) -> list[{ctx.singular_class}Out]: ...
            async def get_by_id(self, {ctx.singular}_id: int) -> {ctx.singular_class}Out | None: ...
            async def create(self, data: {ctx.singular_class}Create) -> {ctx.singular_class}Out: ...
            async def update(
                self, {ctx.singular}_id: int, data: {ctx.singular_class}Update
            ) -> {ctx.singular_class}Out | None: ...
            async def delete(self, {ctx.singular}_id: int) -> bool: ...
        '''
