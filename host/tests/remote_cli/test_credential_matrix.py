"""Credential matrix: what each kind of token may do through ``smdev`` (#1178).

Three credentials (a platform admin's PAT, a tenant admin's PAT, a tenant's
service key) against host-level routes (``/api/users/admin``, system settings,
tenant create), tenant-level routes (members, invitations) and content routes.
The expectations come from the server's guards, not from the CLI: a refusal
arrives as HTTP 403 and the CLI exits 4.
"""

from __future__ import annotations

import json
import uuid

import pytest
from _api_tokens_support import CSRF_HEADERS, create_pat, create_service_key  # ty: ignore[import-not-found]
from simple_module_core.access.tenancy import TenantRole
from simple_module_test.web.tenant_client import create_user, session_client

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_AUTH = 4  # HTTP 401/403
USE = "api_tokens.use"
USERS_VIEW = "users.manage"
SETTINGS_VIEW = "settings.view"
PLATFORM_MANAGE = "tenants.platform.manage"
MEMBERS_VIEW = "tenants.members.view"
MEMBERS_MANAGE = "tenants.members.manage"
FLAGS_VIEW = "feature_flags.view"

LIST_USERS = ("users", "admin-list-users")
UPSERT_SYSTEM = ("settings", "upsert-system-setting")
CREATE_TENANT = ("tenants", "create-tenant")
LIST_MEMBERS = ("tenants", "list-members")
INVITE = ("tenants", "invite")
LIST_FLAGS = ("feature-flags", "list-flags")
LIST_SETTINGS = ("settings", "list-settings")


async def _login(smdev, token: str) -> None:
    await smdev.add_env()
    result = await smdev.login(token)
    assert result.exit_code == 0, result.output
    smdev.transport.requests.clear()


async def _tenant_admin_token(app, tenant_id: str, scopes: list[str]) -> str:
    """A PAT of a non-platform user holding the tenant ``admin`` role in *tenant_id*."""
    from tenants.core.constants import SESSION_ACTIVE_TENANT
    from tenants.models import Membership
    from tenants.resolution.resolver import forget

    email = f"tadmin-{uuid.uuid4().hex[:8]}@example.com"
    user_id = await create_user(app, email)
    async with app.state.sm.db.session_factory() as session:
        session.add(
            Membership(tenant_id=tenant_id, user_id=user_id, role=TenantRole.ADMIN, email=email)
        )
        await session.commit()
    forget(user_id)
    data = {
        "user_id": user_id,
        SESSION_ACTIVE_TENANT: tenant_id,
        "sm_csrf_token": CSRF_HEADERS["X-CSRF-Token"],
    }
    async with session_client(app, data) as client:
        return (await create_pat(client, scopes))["token"]


async def _service_key(app, admin, roles: list[str], scopes: list[str]) -> str:
    resp = await create_service_key(admin.client, name="svc", roles=roles, scopes=scopes)
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


async def _run(smdev, *args: str):
    return await smdev.run("--env", "local", *args, "-o", "json")


# ---- platform-admin PAT pinned to tenant T ----------------------------------------------


async def test_platform_admin_pat_host_level_ops_succeed(smdev, make_actor):
    admin = await make_actor()
    token = await smdev.token_for(admin)
    await _login(smdev, token)
    listed = await _run(smdev, *LIST_USERS)
    assert listed.exit_code == EXIT_OK, listed.output
    upsert = await _run(
        smdev, *UPSERT_SYSTEM, "matrix.key", "--set", "value=1", "--set", "description=m"
    )
    assert upsert.exit_code == EXIT_OK, upsert.output
    created = await _run(smdev, *CREATE_TENANT, "--set", "name=Matrix Org")
    assert created.exit_code == EXIT_OK, created.output


async def test_platform_admin_pat_is_capped_by_its_scopes(smdev, make_actor):
    admin = await make_actor()
    token = await smdev.token_for(admin, [USE, USERS_VIEW])
    await _login(smdev, token)
    assert (await _run(smdev, *LIST_USERS)).exit_code == EXIT_OK
    for cmd in (
        (*UPSERT_SYSTEM, "matrix.key", "--set", "value=1"),
        (*CREATE_TENANT, "--set", "name=Nope"),
    ):
        result = await _run(smdev, *cmd)
        assert result.exit_code == EXIT_AUTH, (cmd, result.output)


# ---- tenant-admin PAT of T ---------------------------------------------------------------


async def test_tenant_admin_pat_tenant_level_ok_host_level_refused(smdev, make_actor, app):
    owner = await make_actor()
    token = await _tenant_admin_token(app, owner.tenant_id, [USE, MEMBERS_VIEW, MEMBERS_MANAGE])
    await _login(smdev, token)
    members = await _run(smdev, *LIST_MEMBERS)
    assert members.exit_code == EXIT_OK, members.output
    invite = await _run(
        smdev,
        *INVITE,
        "--set",
        f"email=new-{uuid.uuid4().hex[:6]}@example.com",
        "--set",
        "role=member",
    )
    assert invite.exit_code == EXIT_OK, invite.output
    for cmd in (
        LIST_USERS,
        (*UPSERT_SYSTEM, "matrix.key", "--set", "value=1"),
        (*CREATE_TENANT, "--set", "name=Nope"),
    ):
        result = await _run(smdev, *cmd)
        assert result.exit_code == EXIT_AUTH, (cmd, result.output)


# ---- service key of T --------------------------------------------------------------------


async def test_service_key_content_per_roles_members_refused(smdev, make_actor, app):
    app.state.sm.permissions.map_role("user", [FLAGS_VIEW, SETTINGS_VIEW])
    admin = await make_actor()
    token = await _service_key(app, admin, ["user"], [FLAGS_VIEW, SETTINGS_VIEW])
    await _login(smdev, token)
    assert (await _run(smdev, *LIST_FLAGS)).exit_code == EXIT_OK
    assert (await _run(smdev, *LIST_SETTINGS)).exit_code == EXIT_OK
    for cmd in (LIST_MEMBERS, (*INVITE, "--set", "email=x@example.com", "--set", "role=member")):
        result = await _run(smdev, *cmd)
        assert result.exit_code == EXIT_AUTH, (cmd, result.output)
        assert "Permission required" in result.output, (cmd, result.output)


async def test_service_key_holding_member_permissions_still_has_no_tenant(smdev, make_actor, app):
    """Observed, differs from "members: 403 by role": even when the key's role carries
    `tenants.members.view`, the membership-based tenant resolver finds no tenant for a
    service key, so the answer is still 403 (`tenant_required`)."""
    app.state.sm.permissions.map_role("user", [MEMBERS_VIEW])
    admin = await make_actor()
    await _login(smdev, await _service_key(app, admin, ["user"], [MEMBERS_VIEW]))
    result = await _run(smdev, *LIST_MEMBERS)
    assert result.exit_code == EXIT_AUTH, result.output
    assert "tenant_required" in result.output, result.output


# ---- tenant-level route, another tenant --------------------------------------------------


async def _credentials(smdev, make_actor, app) -> dict[str, str]:
    app.state.sm.permissions.map_role("user", [MEMBERS_VIEW, FLAGS_VIEW])
    admin = await make_actor()
    return {
        "platform-admin pat": await smdev.token_for(admin),
        "tenant-admin pat": await _tenant_admin_token(
            app, admin.tenant_id, [USE, MEMBERS_VIEW, MEMBERS_MANAGE]
        ),
        "service key": await _service_key(app, admin, ["user"], [MEMBERS_VIEW, FLAGS_VIEW]),
    }


@pytest.mark.parametrize("kind", ["platform-admin pat", "tenant-admin pat", "service key"])
async def test_tenant_level_route_in_another_tenant_is_refused(smdev, make_actor, app, kind):
    creds = await _credentials(smdev, make_actor, app)
    other = await make_actor()  # a second tenant, not the one the credential is pinned to
    await _login(smdev, creds[kind])
    result = await smdev.run(
        "--env", "local", "--tenant", other.tenant_id, *LIST_MEMBERS, "-o", "json"
    )
    # Refused client-side: the stored login is for another tenant (usage error, exit 1).
    assert result.exit_code == EXIT_USAGE, result.output
    assert not [r for r in smdev.transport.requests if "/current/members" in r.url.path]


@pytest.mark.parametrize("kind", ["platform-admin pat", "tenant-admin pat"])
async def test_tenant_level_route_only_ever_shows_the_pinned_tenant(smdev, make_actor, app, kind):
    creds = await _credentials(smdev, make_actor, app)
    other = await make_actor()  # the CLI never sends a tenant id; the token's pin decides
    await _login(smdev, creds[kind])
    result = await _run(smdev, *LIST_MEMBERS)
    assert result.exit_code == EXIT_OK, result.output
    data = json.loads(result.output)
    emails = {m["email"] for m in (data["items"] if isinstance(data, dict) else data)}
    assert other.email not in emails


# ---- PAT mutation on a RequiresCsrf route ------------------------------------------------


async def test_pat_mutation_on_requires_csrf_route_needs_no_token(smdev, make_actor):
    """``POST /api/dashboard/doctor/rerun`` declares ``RequiresCsrf``; a PAT sends no token."""
    admin = await make_actor()
    await _login(smdev, await smdev.token_for(admin))
    result = await _run(smdev, "dashboard", "doctor-rerun")
    assert result.exit_code == EXIT_OK, result.output
    sent = [r for r in smdev.transport.requests if r.url.path.endswith("/doctor/rerun")]
    assert sent and all("x-csrf-token" not in r.headers for r in sent)
    assert all("authorization" in r.headers for r in sent)
