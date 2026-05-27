"""SQLModel tables for the users module — one entity per file under this package.

Existing imports like ``from users.models import User`` keep working via the
re-exports below.
"""

from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase

from users.models._base import Base
from users.models.access_token import UserAccessToken
from users.models.oauth_account import OAuthAccount
from users.models.refresh_token import RefreshToken
from users.models.role import Role
from users.models.user import User
from users.models.user_role import UserRole

__all__ = [
    "Base",
    "OAuthAccount",
    "RefreshToken",
    "Role",
    "SQLAlchemyAccessTokenDatabase",
    "SQLAlchemyUserDatabase",
    "User",
    "UserAccessToken",
    "UserRole",
]
