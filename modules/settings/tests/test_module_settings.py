from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from pydantic import Field
from pydantic_settings import BaseSettings
from settings._module_settings import collect_module_settings
from settings.services import SettingsServices
from settings.settings import SettingsSettings
from simple_module_core.module import ModuleMeta
from simple_module_core.services import Services


class _DemoCfg(BaseSettings):
    allow: bool = False
    port: int = Field(default=25, json_schema_extra={"requires_restart": True, "group": "SMTP"})
    host: str = Field(default="localhost", json_schema_extra={"group": "SMTP"})
    secret: str = ""


class _DemoModule:
    meta = ModuleMeta(name="Demo")


# Force ``type(mod).__module__`` to resolve to "demo" so _package_of returns
# "demo" (matching the app.state.demo attribute the collector reads).
_DemoModule.__module__ = "demo"


@dataclass
class _DemoServices:
    settings: _DemoCfg


def test_collect_exposes_type_requires_restart_group():
    app = FastAPI()
    app.state.settings = SettingsServices(settings=SettingsSettings())
    app.state.settings.module_registry.register("demo", _DemoCfg)

    app.state.demo = _DemoServices(settings=_DemoCfg())
    app.state.sm = Services(
        settings=None,  # type: ignore[arg-type]
        db=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
        menu_registry=None,  # type: ignore[arg-type]
        permissions=None,  # type: ignore[arg-type]
        feature_flags=None,  # type: ignore[arg-type]
        health_registry=None,  # type: ignore[arg-type]
        i18n_registry=None,  # type: ignore[arg-type]
        inertia_config=None,  # type: ignore[arg-type]
        modules=(_DemoModule(),),  # type: ignore[arg-type]
    )

    views = collect_module_settings(app)
    demo = next(v for v in views if v.package == "demo")
    by_name = {f.name: f for f in demo.fields}
    assert by_name["allow"].type == "bool"
    assert by_name["port"].type == "int"
    assert by_name["port"].requires_restart is True
    assert by_name["port"].group == "SMTP"
    assert by_name["host"].group == "SMTP"
    assert by_name["allow"].group is None
    assert by_name["secret"].is_secret is True
