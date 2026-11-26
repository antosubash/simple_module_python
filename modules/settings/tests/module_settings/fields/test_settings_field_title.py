"""A field's pydantic ``title`` reaches the editor as its fallback label.

Bundled modules label their fields through ``settings_form`` locale keys; a
third-party module that has none still gets a readable label when it declares
``Field(title=...)``.
"""

from pydantic import Field
from settings.module_settings.discovery import ModuleSettingsView, _field_view
from settings.module_settings.props import serialize
from simple_module_core.settings.settings_base import DbBackedSettings


def test_title_is_serialized_and_absent_title_is_none():
    class ExampleSettings(DbBackedSettings):
        smtp_host: str = Field(default="", title="Mail server")
        plain: str = ""

    fields = [_field_view(name, ExampleSettings(), "") for name in ExampleSettings.model_fields]
    view = ModuleSettingsView("Example", "example", "", "ExampleSettings", fields)
    result = serialize([view])[0]["fields"]
    assert [field["title"] for field in result] == ["Mail server", None]
