"""``register_resource_types`` reaches ``app.state.sm.resource_types`` (GH #526)."""

from __future__ import annotations

import simple_module_hosting.app_builder as app_builder
from _resacc_models import POLICY, ResaccDoc
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.resources import ResourceType, ResourceTypeRegistry
from simple_module_db.resource_policy import select_by_id
from simple_module_hosting.app_builder import create_app


class _ResaccModule(ModuleBase):
    meta = ModuleMeta(name="ResaccFixture")

    def register_resource_types(self, registry: ResourceTypeRegistry) -> None:
        registry.register(
            ResourceType(name="resacc.doc", policy=POLICY, select_by_id=select_by_id(ResaccDoc))
        )


def test_module_resource_type_reaches_services(monkeypatch, settings):
    real_discover = app_builder.discover_modules
    monkeypatch.setattr(
        app_builder,
        "discover_modules",
        lambda *a, **kw: [*real_discover(*a, **kw), _ResaccModule()],
    )
    app = create_app(settings)
    registered = app.state.sm.resource_types.get("resacc.doc")
    assert registered is not None and registered.policy is POLICY
