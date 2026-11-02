"""Role table — a named role that holds permission strings."""

# NOTE: intentionally no ``from __future__ import annotations`` — SQLModel
# Relationship resolution requires runtime annotations.

import uuid

from fastapi_users_db_sqlalchemy.generics import GUID
from simple_module_core.tenancy import TENANT_ROLE_PREFIX
from simple_module_db.mixins import AuditMixin
from sqlalchemy.orm import validates
from sqlmodel import Field, Relationship

from users.models._base import Base
from users.models.user import User
from users.models.user_role import UserRole


class Role(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A named role that can hold a set of permission strings."""

    __tablename__ = "users_role"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_type=GUID,
        primary_key=True,
    )
    name: str = Field(max_length=64, unique=True, index=True)
    description: str | None = Field(default=None, max_length=255)

    users: list[User] = Relationship(
        link_model=UserRole,
        back_populates="roles",
        sa_relationship_kwargs={"lazy": "noload"},
    )

    @validates("name")
    def _reject_tenant_namespace(self, _key: str, value: str) -> str:
        """``tenant:*`` is the synthetic per-tenant principal namespace (#377).

        A platform ``Role`` row with that prefix would be indistinguishable from
        the active tenant's membership role on a principal, so the name is
        refused at the model, whichever path (service, CLI, seed) sets it.
        """
        if isinstance(value, str) and value.casefold().startswith(TENANT_ROLE_PREFIX):
            raise ValueError(
                f"Role names starting with {TENANT_ROLE_PREFIX!r} are reserved for tenant roles"
            )
        return value
