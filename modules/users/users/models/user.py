"""Local user table.

Column surface mirrors fastapi-users' ``SQLAlchemyBaseUserTableUUID`` so the
``SQLAlchemyUserDatabase`` adapter binds to it without inheriting from the
upstream base class (which uses SQLAlchemy ``Mapped`` and is incompatible with
SQLModel's metaclass).
"""

# NOTE: intentionally no ``from __future__ import annotations`` — SQLModel
# Relationship resolution requires runtime annotations (not stringified ones)
# for forward references like ``list["Role"]`` to work correctly.

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from fastapi_users_db_sqlalchemy.generics import GUID
from simple_module_db.mixins import AuditMixin
from sqlalchemy import DateTime, Index, false, text
from sqlmodel import Field, Relationship

from users.models._base import Base
from users.models.user_role import UserRole

if TYPE_CHECKING:
    # Resolved at runtime by SQLModel via the string forward ref;
    # this import only feeds the type checker.
    from users.models.oauth_account import OAuthAccount
    from users.models.role import Role


class User(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """Local user. Column surface mirrors fastapi-users' SQLAlchemyBaseUserTableUUID."""

    __tablename__ = "users_user"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_type=GUID,
        primary_key=True,
    )
    email: str = Field(max_length=320, unique=True, index=True)
    # Nullable: external (SSO) users have NO local password. fastapi-users sets
    # this for password accounts; the OAuth path leaves it ``None`` (see
    # ``UserManager.on_after_register``).
    hashed_password: str | None = Field(default=None, max_length=1024)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    # True for users provisioned via an external IdP (Microsoft/Entra, Google,
    # GitHub, generic OIDC). They authenticate only through SSO; password login
    # and password reset are refused. Roles are still assigned locally.
    is_external: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": false()},
    )

    full_name: str | None = Field(default=None, max_length=255)
    tenant_id: str | None = Field(default=None, max_length=50, index=True)
    disabled_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    last_login_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        index=True,
    )
    # Set when an admin created this account on someone's behalf; ``None`` for
    # a self-signup. Both shapes are otherwise identical rows
    # (``is_active and not is_verified``), and they call for opposite actions —
    # resend the invite, versus wait for a person who already has the mail — so
    # the distinction has to be stored rather than guessed. Also dates the
    # invite, which is what makes "expires in 5d" derivable from the token
    # lifetime.
    invited_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    # Bumped by "sign out everywhere". Browser auth is a signed cookie, not a
    # server-side session store, so there is no row to delete for a device that
    # is no longer in the owner's hands; every session stamps this value at
    # login and the auth provider refuses any that no longer matches.
    session_version: int = Field(
        default=0,
        sa_column_kwargs={"server_default": text("0")},
    )

    roles: list["Role"] = Relationship(
        link_model=UserRole,
        back_populates="users",
        sa_relationship_kwargs={"lazy": "noload"},
    )

    # fastapi-users' SQLAlchemyUserDatabase.add_oauth_account does
    # ``user.oauth_accounts.append(...)``, so this attribute must exist.
    # ``selectin`` + ``delete-orphan`` is required for the ORM cascade to remove
    # a user's OAuth accounts when the user is deleted — SQLite (the default DB)
    # does not enforce the ``ondelete="CASCADE"`` FK, so the cascade must happen
    # in the ORM. To keep this off the hot read path, the auth provider and the
    # ``current_user`` adapter add ``noload(User.oauth_accounts)`` to their
    # queries (see provider.py / db_adapter.py) — only the OAuth association
    # flow (get_by_email) actually materialises the collection.
    oauth_accounts: list["OAuthAccount"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
        },
    )

    # Functional index so the ``lower(email)`` predicate used by
    # ``UserDatabaseWithRoles.get_by_email`` can be served from an index.
    __table_args__ = (Index("ix_users_user_email_lower", text("lower(email)")),)
