"""Permission group headings are translated server-side (TEST-015)."""

from __future__ import annotations

from permissions.service import PermissionService
from simple_module_core.i18n import Translator
from simple_module_core.permissions import PermissionRegistry


def _translator(app, locale: str) -> Translator:
    registry = app.state.sm.i18n_registry
    if locale not in registry.supported_locales:  # test hosts default to ["en"]
        registry.supported_locales = [*registry.supported_locales, locale]
        registry.load()
    return Translator(registry, locale=locale, default_locale="en")


def test_add_group_keeps_label_key():
    registry = PermissionRegistry()
    registry.add_group("Reports", ["reports.view"], label_key="reports.permission_group")
    registry.add_group("Reports", ["reports.edit"])
    (group,) = registry.groups
    assert group.label_key == "reports.permission_group"
    assert group.permissions == ["reports.view", "reports.edit"]


async def test_group_labels_follow_the_locale(app, db_session):
    service = PermissionService(db_session, app.state.sm.permissions)
    german = {g.name: g.label for g in service.list_registered_groups(_translator(app, "de").t)}
    english = {g.name: g.label for g in service.list_registered_groups(_translator(app, "en").t)}
    assert german["Files"] == "Dateien"
    assert german["Feature flags"] == "Feature-Flags"
    assert english["Files"] == "Files"
    # Every registered group resolves to a label, never a raw catalog key.
    assert all(label and "permission_group" not in label for label in german.values())


async def test_without_translator_label_is_the_name(app, db_session):
    service = PermissionService(db_session, app.state.sm.permissions)
    assert all(g.label == g.name for g in service.list_registered_groups())
