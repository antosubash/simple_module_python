"""OIDC policy uses hydrated settings even without the Settings UI (#192)."""

from oidc.core.settings import OidcSettings
from settings.core.invalidation import reload_package
from settings.core.service import SettingService
from settings.module_settings.store import SettingsStore
from simple_module_core.module_settings import module_settings_registry


async def test_boot_hydrates_db_settings_without_settings_ui(oidc_app):
    assert not hasattr(oidc_app.state, "settings")
    assert module_settings_registry(oidc_app).get("oidc") is OidcSettings
    assert oidc_app.state.oidc.settings.client_id == "my-app"
    provider = oidc_app.state.auth.auth_provider
    ctx = provider._claims_to_user_context(
        {"oid": "user", "roles": ["admin"], "preferred_username": "Alice"}, cache_id="uuid"
    )
    assert ctx.roles == ["admin"]
    assert ctx.name == "Alice"
    assert provider._subject({"oid": "object-id", "sub": "pairwise"}) == "object-id"


async def test_mapping_reload_changes_provider_policy(oidc_app):
    provider = oidc_app.state.auth.auth_provider
    claims = {"roles": ["admin"], "realm_access": {"roles": ["editor"]}}
    assert provider._claims_to_user_context(claims, cache_id="uuid").roles == ["admin"]
    async with oidc_app.state.sm.db.session_factory() as db:
        store = SettingsStore(SettingService(db))
        await store.set_override("oidc", "roles_claim_path", "realm_access.roles", "string")
        await store.set_override("oidc", "role_mapping", '{"editor": "writer"}', "json")
        await db.commit()
        await reload_package(oidc_app, oidc_app.state.sm.event_bus, store, "oidc")
    assert oidc_app.state.auth.auth_provider is provider
    assert provider._claims_to_user_context(claims, cache_id="uuid").roles == ["writer"]
