"""Renderer hints survive discovery and the shared API/Inertia serialization."""

from pydantic import Field
from settings.module_settings.discovery import ModuleSettingsView, _field_view
from settings.module_settings.props import serialize
from simple_module_core.settings.settings_base import DbBackedSettings


def test_control_hint_is_serialized():
    class ExampleSettings(DbBackedSettings):
        starts_on: str = Field(default="", json_schema_extra={"control": "date"})
        plain: str = ""
        invalid: str = Field(default="", json_schema_extra={"control": {"bad": True}})

    fields = [_field_view(name, ExampleSettings(), "") for name in ExampleSettings.model_fields]
    view = ModuleSettingsView("Example", "example", "", "ExampleSettings", fields)
    result = serialize([view])[0]["fields"]
    assert [field["control"] for field in result] == ["date", None, None]
