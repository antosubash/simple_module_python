"""The ``ui`` namespace ships with the hosting package (#426)."""

from __future__ import annotations

from simple_module_hosting.i18n_manifest import build_i18n_registry
from simple_module_hosting.settings import Settings


def test_ui_namespace_registered_without_packages_ui(tmp_path):
    assert not (tmp_path / "packages" / "ui").exists()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    registry, extra = build_i18n_registry(settings, [], tmp_path)
    msgs = registry.messages("en")
    assert msgs["ui.nav_groups.navigation"] == "Navigation"
    assert any(ns == "ui" for _, ns, _ in extra)
