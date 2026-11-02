"""The app boots and hydrates settings with the ``settings`` plugin disabled (#500).

The framework owns the module-settings registry, the hydrator and the table,
so host and module settings still come from the DB without the admin UI.
"""

from __future__ import annotations

from simple_module_core.discovery import discover_modules
from simple_module_core.module_settings import get_module_settings_registry
from simple_module_db.stored_settings import Setting

# Settings itself, plus the modules that hard-depend on it.
_EXCLUDED = {"Settings", "Branding", "Mail"}


async def test_boot_without_settings_plugin_hydrates_from_db(settings) -> None:
    from simple_module_hosting.app_builder import create_app
    from simple_module_test._schema import _create_all_tables

    enabled = [m.meta.name for m in discover_modules() if m.meta.name not in _EXCLUDED]
    app = create_app(settings.model_copy(update={"modules_enabled": enabled}))
    await _create_all_tables(app.state.sm.db.engine)
    async with app.state.sm.db.session_factory() as session:
        session.add(Setting(key="host.api_title", value="From the DB", value_type="string"))
        session.add(Setting(key="users.allow_signup", value="true", value_type="bool"))
        await session.commit()

    async with app.router.lifespan_context(app):
        assert not hasattr(app.state, "settings"), "the plugin is disabled"
        registry = get_module_settings_registry(app)
        assert registry is not None
        assert {"host", "users"} <= set(registry.all_packages())
        assert app.state.host.settings.api_title == "From the DB"
        assert app.state.users.settings.allow_signup is True
