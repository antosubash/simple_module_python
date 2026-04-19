"""SQLModel DTOs + the SettingScope enum for the Settings module."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import ConfigDict, model_validator
from sqlmodel import Field, SQLModel

from settings.constants import (
    DESCRIPTION_MAX_LENGTH,
    ERR_SCOPED_REQUIRES_ID,
    ERR_SYSTEM_SCOPE_NO_ID,
    KEY_MAX_LENGTH,
    SCOPE_ID_MAX_LENGTH,
    SCOPE_SYSTEM,
    SCOPE_TENANT,
    SCOPE_USER,
    SYSTEM_SCOPE_ID,
    VALUE_MAX_LENGTH,
)


class SettingScope(StrEnum):
    """Override level for a setting entry."""

    SYSTEM = SCOPE_SYSTEM
    TENANT = SCOPE_TENANT
    USER = SCOPE_USER


def _validate_scope_id(scope: SettingScope, scope_id: str) -> None:
    if scope is SettingScope.SYSTEM and scope_id:
        raise ValueError(ERR_SYSTEM_SCOPE_NO_ID)
    if scope is not SettingScope.SYSTEM and not scope_id:
        raise ValueError(ERR_SCOPED_REQUIRES_ID)


class SettingOut(SQLModel):
    """A setting returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: SettingScope
    scope_id: str
    key: str
    value: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SettingCreate(SQLModel):
    """Payload to create a new setting at an explicit scope."""

    scope: SettingScope = SettingScope.SYSTEM
    scope_id: str = Field(default=SYSTEM_SCOPE_ID, max_length=SCOPE_ID_MAX_LENGTH)
    key: str = Field(min_length=1, max_length=KEY_MAX_LENGTH)
    value: str = Field(max_length=VALUE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)

    @model_validator(mode="after")
    def _check_scope(self) -> SettingCreate:
        _validate_scope_id(self.scope, self.scope_id)
        return self


class SettingUpdate(SQLModel):
    """Payload to update an existing setting by id. Scope cannot change."""

    value: str | None = Field(default=None, max_length=VALUE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)


class SettingUpsert(SQLModel):
    """Payload for upsert operations (key/value + optional description)."""

    value: str = Field(max_length=VALUE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
