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


def test_env_source_var_names_only_a_variable_that_is_set(monkeypatch):
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class EnvSettings(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="SM_DEMOX_")
        host: str = ""
        broker: str = ""

    monkeypatch.setenv("SM_DEMOX_HOST", "mail.example")
    settings = EnvSettings()
    # ``broker`` reported env-supplied without its own variable, as when a
    # shared SM_REDIS_URL feeds it: the badge must not name SM_DEMOX_BROKER.
    supplied = frozenset({"host", "broker"})
    host = _field_view("host", settings, "SM_DEMOX_", env_supplied=supplied)
    broker = _field_view("broker", settings, "SM_DEMOX_", env_supplied=supplied)
    assert host.env_source_var == "SM_DEMOX_HOST"
    assert broker.env_set and broker.env_source_var is None
