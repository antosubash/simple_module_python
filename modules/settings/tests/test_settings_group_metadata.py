"""Group metadata must match the settings view's optional string contract."""

import pytest
from pydantic import Field
from pydantic_settings import BaseSettings
from settings._module_settings import _field_view


@pytest.mark.parametrize("group", [False, 42, [], {}, None, "SMTP"])
def test_settings_group_metadata_accepts_only_strings(group):
    class Config(BaseSettings):
        host: str = Field(default="localhost", json_schema_extra={"group": group})

    view = _field_view("host", Config(), "SM_DEMO_")

    assert view.group == (group if isinstance(group, str) else None)
