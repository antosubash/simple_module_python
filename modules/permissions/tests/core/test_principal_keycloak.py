"""A Keycloak cache row knows no IdP roles; it still gets registered grants."""

import uuid

from keycloak.module import KeycloakModule
from permissions.module import PermissionsModule
from simple_module_core.principals import build_principal_registry
from simple_module_db.principals import bind_principal_registry, principal_for
from tenants.module import TenantsModule


async def test_keycloak_unknown_roles(db_session, db_state, settings):
    from keycloak.models import KeycloakUserCache
    from permissions.models import UserPermission
    from tenants.models import Membership, Tenant

    user_id = uuid.uuid4()
    db_session.add(KeycloakUserCache(id=user_id, keycloak_sub="test-sub", email="idp@example.com"))
    db_session.add(Tenant(id="own", slug="idp", name="IdP"))
    await db_session.flush()
    db_session.add(Membership(user_id=str(user_id), tenant_id="own", role="member"))
    db_session.add(UserPermission(user_id=user_id, permission_key="test.direct"))
    await db_session.commit()
    registry = build_principal_registry(
        [KeycloakModule(), TenantsModule(), PermissionsModule()], settings
    )
    registry.permissions.map_role("tenant:member", ["test.member"])
    bind_principal_registry(db_state.session_factory, registry)
    async with db_state.session_factory() as db:
        who = await principal_for(db, str(user_id), "own")
    assert who.permissions == {"test.direct", "test.member", "tenants.members.view"}
    assert not who.has("*")
