"""Provider roles drive the editor and the shared principal builder (#953)."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from keycloak.core.settings import KeycloakSettings
from keycloak.identity.provider import KeycloakAuthProvider
from keycloak.module import KeycloakModule
from oidc.core.settings import OidcSettings
from oidc.identity.provider import OidcAuthProvider
from oidc.module import OidcModule
from permissions.core.service import PermissionService
from simple_module_core.access.permissions import PermissionRegistry
from simple_module_core.access.principal_permissions import load_principal
from simple_module_core.access.role_directory import get_role_directory
from simple_module_core.access.user_directory import get_user_directory
from simple_module_db.engine.transaction import finalize_session
from users.core.directory import UsersDirectory
from users.models import Role, User, UserRole


@pytest.mark.parametrize(
    "module,settings_cls,provider_cls",
    [
        (KeycloakModule, KeycloakSettings, KeycloakAuthProvider),
        (OidcModule, OidcSettings, OidcAuthProvider),
    ],
)
async def test_provider_registration_and_live_role_mapping(module, settings_cls, provider_cls):
    app = FastAPI()
    app.state.auth = SimpleNamespace()
    module().register_settings(app)
    state = getattr(app.state, module.meta.name.lower())
    state.settings = settings_cls(role_mapping={"realm-editor": "editor"})
    roles = get_role_directory(app)
    assert [r.name for r in await roles.list_roles(None)] == ["editor"]
    assert not roles.editable
    assert await roles.user_roles(None, str(uuid.uuid4())) is None
    registry = PermissionRegistry()
    registry.map_role("editor", ["products.view"])
    # OIDC presets choose different claim paths; use the configured path.
    state.settings.roles_claim_path = "realm_access.roles"
    actor = provider_cls(state.settings)._claims_to_user_context(
        {"sub": "subject", "realm_access": {"roles": ["realm-editor"]}},
        cache_id=str(uuid.uuid4()),
    )
    principal = await load_principal(None, actor, registry)
    assert principal.roles == {"editor"}
    assert principal.has("products.view")


@pytest.mark.parametrize(
    "module,settings_cls,provider_cls",
    [
        (KeycloakModule, KeycloakSettings, KeycloakAuthProvider),
        (OidcModule, OidcSettings, OidcAuthProvider),
    ],
)
async def test_external_editor_maps_claim_roles_to_permissions(
    db_session,
    module,
    settings_cls,
    provider_cls,
):
    app = FastAPI()
    app.state.auth = SimpleNamespace()
    module().register_settings(app)
    config = settings_cls(
        roles_claim_path="realm_access.roles", role_mapping={"realm-editor": "editor"}
    )
    getattr(app.state, module.meta.name.lower()).settings = config
    registry = PermissionRegistry()
    registry.add("products.view")
    service = PermissionService(
        db_session, registry, get_user_directory(app), role_directory=get_role_directory(app)
    )
    rows = await service.list_roles_with_counts()
    role, count = rows[0]
    assert (role.name, role.label, count) == ("editor", "editor", 0)
    assert await service.set_role_permissions(role.id, ["products.view"]) is not None
    await finalize_session(db_session)
    # These are verified claims at the provider boundary, not guessed cached roles.
    actor = provider_cls(config)._claims_to_user_context(
        {"sub": "subject", "realm_access": {"roles": ["realm-editor"]}},
        cache_id=str(uuid.uuid4()),
    )
    principal = await load_principal(None, actor, registry, db=db_session)
    assert principal.has("products.view")
    assert await service.role_directory.user_roles(db_session, actor.id) is None
    assert (await service.list_roles_with_counts())[0][1] == 1


async def test_local_role_directory_preserves_ids_and_memberships(db_session):
    role = Role(name="editor", description="Edits products")
    user = User(email="role-directory@test", hashed_password="unused")
    db_session.add_all([role, user])
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    await db_session.flush()
    directory = UsersDirectory()
    assert directory.editable
    assert await directory.user_roles(db_session, str(user.id)) == ("editor",)
    assert await directory.user_roles(db_session, "unknown") is None
    rows = await directory.list_roles(db_session)
    assert [(r.id, r.name, r.label, r.description) for r in rows] == [
        (role.id, "editor", "editor", "Edits products")
    ]
