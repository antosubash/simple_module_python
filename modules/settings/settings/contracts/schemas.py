"""SQLModel DTOs + SettingScope / SettingValueType enums."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum

from pydantic import ConfigDict, model_validator
from sqlmodel import Field, SQLModel

from settings.constants import (
    DESCRIPTION_MAX_LENGTH,
    ERR_SCOPED_REQUIRES_ID,
    ERR_SYSTEM_SCOPE_NO_ID,
    ERR_VALUE_MISMATCH,
    KEY_MAX_LENGTH,
    SCOPE_ID_MAX_LENGTH,
    SCOPE_SYSTEM,
    SCOPE_TENANT,
    SCOPE_USER,
    SYSTEM_SCOPE_ID,
    VALUE_MAX_LENGTH,
    VALUE_TYPE_BOOL,
    VALUE_TYPE_FLOAT,
    VALUE_TYPE_INT,
    VALUE_TYPE_JSON,
    VALUE_TYPE_STRING,
)

_BOOL_LITERALS = frozenset(
    {"true", "false", "1", "0", "t", "f", "yes", "no", "y", "n", "on", "off"}
)


class SettingScope(StrEnum):
    """Override level for a setting entry."""

    SYSTEM = SCOPE_SYSTEM
    TENANT = SCOPE_TENANT
    USER = SCOPE_USER


class SettingValueType(StrEnum):
    """How the stored ``value`` string should be interpreted."""

    STRING = VALUE_TYPE_STRING
    BOOL = VALUE_TYPE_BOOL
    INT = VALUE_TYPE_INT
    FLOAT = VALUE_TYPE_FLOAT
    JSON = VALUE_TYPE_JSON


def _validate_scope_id(scope: SettingScope, scope_id: str) -> None:
    if scope is SettingScope.SYSTEM and scope_id:
        raise ValueError(ERR_SYSTEM_SCOPE_NO_ID)
    if scope is not SettingScope.SYSTEM and not scope_id:
        raise ValueError(ERR_SCOPED_REQUIRES_ID)


def _validate_value_matches_type(value: str, value_type: SettingValueType) -> None:
    """Ensure ``value`` parses as the declared type. Empty values are always ok."""
    if value == "":
        return
    if value_type is SettingValueType.STRING:
        return
    if value_type is SettingValueType.BOOL:
        if value.strip().lower() not in _BOOL_LITERALS:
            raise ValueError(ERR_VALUE_MISMATCH)
        return
    if value_type is SettingValueType.INT:
        try:
            int(value)
        except ValueError as exc:
            raise ValueError(ERR_VALUE_MISMATCH) from exc
        return
    if value_type is SettingValueType.FLOAT:
        try:
            float(value)
        except ValueError as exc:
            raise ValueError(ERR_VALUE_MISMATCH) from exc
        return
    if value_type is SettingValueType.JSON:
        try:
            json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(ERR_VALUE_MISMATCH) from exc


class SettingOut(SQLModel):
    """A setting returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scope: SettingScope
    scope_id: str
    key: str
    value: str
    value_type: SettingValueType = SettingValueType.STRING
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SettingCreate(SQLModel):
    """Payload to create a new setting at an explicit scope."""

    scope: SettingScope = SettingScope.SYSTEM
    scope_id: str = Field(default=SYSTEM_SCOPE_ID, max_length=SCOPE_ID_MAX_LENGTH)
    key: str = Field(min_length=1, max_length=KEY_MAX_LENGTH)
    value: str = Field(max_length=VALUE_MAX_LENGTH)
    value_type: SettingValueType = SettingValueType.STRING
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)

    @model_validator(mode="after")
    def _check(self) -> SettingCreate:
        _validate_scope_id(self.scope, self.scope_id)
        _validate_value_matches_type(self.value, self.value_type)
        return self


class SettingUpdate(SQLModel):
    """Payload to update an existing setting by id. Scope cannot change."""

    value: str | None = Field(default=None, max_length=VALUE_MAX_LENGTH)
    value_type: SettingValueType | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)

    @model_validator(mode="after")
    def _check(self) -> SettingUpdate:
        if self.value is not None and self.value_type is not None:
            _validate_value_matches_type(self.value, self.value_type)
        return self


class SettingUpsert(SQLModel):
    """Payload for upsert operations (value + optional type + description).

    ``value_type`` is optional: when absent on an update it preserves the
    existing row's type, and on a create it defaults to ``STRING``.
    """

    value: str = Field(max_length=VALUE_MAX_LENGTH)
    value_type: SettingValueType | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)

    @model_validator(mode="after")
    def _check(self) -> SettingUpsert:
        if self.value_type is not None:
            _validate_value_matches_type(self.value, self.value_type)
        return self
