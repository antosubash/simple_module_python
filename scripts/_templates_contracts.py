"""Template generators for the contracts/ sub-package (DTOs only).

Modules do not ship a Protocol for their service by default. Consumers
type-hint against the concrete service class exported from
``<module>.service`` — add a Protocol only when you expect multiple
implementations or an extension point (see ``file_storage.StorageBackend``
for the pattern).
"""

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

        __all__ = [
            "{ctx.singular_class}Create",
            "{ctx.singular_class}Out",
            "{ctx.singular_class}Update",
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
