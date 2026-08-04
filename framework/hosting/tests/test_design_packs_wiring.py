"""``create_app`` must collect module design packs onto ``app.state.design_packs``.

Branding reads this registry twice — the view builds its dropdown from it, and
the API validates a submitted slug against it. If the hook were never called,
or the populated registry never reached ``app.state``, branding would offer an
empty dropdown and reject every pack, with nothing in the logs to explain why.
"""

from __future__ import annotations

import simple_module_hosting.app_builder as app_builder
from simple_module_core.design_packs import DesignPack, DesignPackRegistry
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_hosting.app_builder import create_app

_PACK = DesignPack(value="pack-fixture", label="Pack Fixture")


class _PackModule(ModuleBase):
    """A module whose only contribution is one design pack."""

    meta = ModuleMeta(name="PackFixture")

    def register_design_packs(self, registry: DesignPackRegistry) -> None:
        registry.register(_PACK)


def test_registry_is_published_on_app_state(settings):
    app = create_app(settings)
    assert isinstance(app.state.design_packs, DesignPackRegistry)


def test_module_registered_pack_reaches_app_state(monkeypatch, settings):
    real_discover = app_builder.discover_modules

    def _with_pack_module(*args, **kwargs):
        return [*real_discover(*args, **kwargs), _PackModule()]

    monkeypatch.setattr(app_builder, "discover_modules", _with_pack_module)

    app = create_app(settings)

    assert app.state.design_packs.has("pack-fixture")
    assert _PACK in app.state.design_packs.all()


def test_registry_is_also_reachable_through_services(settings):
    # ``app.state.sm`` is the aggregate every other registry is published on;
    # design packs should not be the one exception a module author has to
    # remember a different lookup for.
    app = create_app(settings)
    assert app.state.sm.design_packs is app.state.design_packs
