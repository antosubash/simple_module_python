"""Per-type role registration, SQL access and delegated sharing (#707)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from _sharing_support import FakeDirectory, SharingTestNote, create_note_table
from sharing.constants import ROLE_MAX
from sharing.contracts.schemas import ShareGrant
from sharing.policy import roles_granting, share_exists_for
from sharing.service import SharingError, SharingService
from simple_module_core.datetimes import utcnow
from simple_module_core.resources import (
    ACTION_EDIT,
    ACTION_SHARE,
    ACTION_VIEW,
    ResourcePrincipal,
    ResourceType,
    ResourceTypeError,
    ResourceTypeRegistry,
)
from simple_module_db.resource_policy import OwnedResourcePolicy, select_by_id
from simple_module_db.tenancy import tenant_context
from sqlmodel import select

TYPE = "sharing_test.custom"
OWNER, MANAGER, READER, OTHER = (str(uuid.UUID(int=n)) for n in (11, 12, 13, 14))
ROLES = {
    "validator": (ACTION_VIEW, "validate"),
    "manager": (ACTION_VIEW, ACTION_SHARE),
    "reviewer": (ACTION_VIEW, ACTION_EDIT, "review"),
}


def declaration(**kwargs):
    policy = OwnedResourcePolicy(
        SharingTestNote.owner_id,
        bypass_perm=None,
        share_exists=share_exists_for(TYPE, SharingTestNote.id, roles=kwargs.get("share_roles")),
    )
    return ResourceType(TYPE, policy, select_by_id(SharingTestNote), **kwargs)


@pytest.mark.parametrize("actions", [(), (ACTION_EDIT,), (ACTION_SHARE,), ("validate",)])
def test_registration_rejects_roles_without_view(actions):
    resource = declaration(share_roles={"broken": actions})
    with pytest.raises(ResourceTypeError, match="view"):
        ResourceTypeRegistry().register(resource)


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (ACTION_VIEW, ("validator", "manager", "reviewer")),
        (ACTION_SHARE, ("manager",)),
        ("validate", ("validator",)),
        (ACTION_EDIT, ("reviewer",)),
        ("delete", ()),
    ],
)
def test_roles_granting_uses_declared_mapping(action, expected):
    assert roles_granting(action, roles=ROLES) == expected


def test_empty_roles_do_not_fall_back_to_defaults():
    assert roles_granting(ACTION_VIEW, roles={}) == ()
    assert (
        share_exists_for(TYPE, SharingTestNote.id, roles={})(
            ResourcePrincipal(MANAGER), ACTION_VIEW
        )
        is None
    )
    ResourceTypeRegistry().register(declaration(share_roles={}))


def test_default_roles_remain_view_and_edit():
    assert roles_granting(ACTION_VIEW) == ("view", "edit")
    assert roles_granting(ACTION_EDIT) == ("edit",)
    assert roles_granting(ACTION_SHARE) == ()


@pytest.mark.parametrize("subset", [(ACTION_VIEW,), (ACTION_EDIT,), ()])
def test_legacy_subsets_warn_and_translate_to_roles(subset):
    with pytest.warns(DeprecationWarning, match="shareable_actions.*0.1.0"):
        resource = declaration(shareable_actions=subset)
    ResourceTypeRegistry().register(resource)
    assert tuple(resource.share_roles) == subset
    if ACTION_EDIT in subset:
        assert resource.share_roles[ACTION_EDIT] == (ACTION_VIEW, ACTION_EDIT)


@pytest.fixture
async def custom_env(db_session, request):
    await create_note_table(await db_session.connection())
    note = SharingTestNote(owner_id=uuid.UUID(OWNER), title="custom")
    db_session.add(note)
    await db_session.flush()
    resource = declaration(share_roles=getattr(request, "param", ROLES))
    registry = ResourceTypeRegistry()
    registry.register(resource)
    service = SharingService(db_session, registry, FakeDirectory(OWNER, MANAGER, READER, OTHER))
    return service, note, resource


def grant_data(note, subject=MANAGER, role="manager"):
    return ShareGrant(resource_type=TYPE, resource_id=str(note.id), subject_id=subject, role=role)


async def visible(service, resource, user, action):
    stmt = resource.policy.filter(ResourcePrincipal(user), action, select(SharingTestNote))
    return [row.title for row in (await service.db.execute(stmt)).scalars()]


@pytest.mark.parametrize(
    ("role", "action", "allowed"),
    [
        ("validator", "validate", True),
        ("validator", ACTION_EDIT, False),
        ("reviewer", "review", True),
        ("reviewer", "validate", False),
        ("manager", ACTION_SHARE, True),
        ("manager", ACTION_EDIT, False),
    ],
)
async def test_registered_roles_and_sql_agree(custom_env, role, action, allowed):
    service, note, resource = custom_env
    with tenant_context("t1"):
        await service.grant(ResourcePrincipal(OWNER), grant_data(note, role=role))
        assert await visible(service, resource, MANAGER, ACTION_VIEW) == ["custom"]
        assert await visible(service, resource, MANAGER, action) == (["custom"] if allowed else [])
        assert await visible(service, resource, OTHER, ACTION_VIEW) == []


async def test_manager_lists_grants_any_role_and_revokes(custom_env):
    service, note, _ = custom_env
    with tenant_context("t1"):
        manager = await service.grant(ResourcePrincipal(OWNER), grant_data(note))
        who = ResourcePrincipal(MANAGER)
        assert [s.id for s in await service.for_resource(who, TYPE, str(note.id))] == [manager.id]
        for role in ROLES:
            granted = await service.grant(who, grant_data(note, READER, role))
            assert granted.role == role
        await service.revoke(who, granted.id)
        assert [s.id for s in await service.for_resource(who, TYPE, str(note.id))] == [manager.id]


@pytest.mark.parametrize("operation", ["grant", "list", "revoke"])
async def test_non_manager_cannot_manage_other_shares(custom_env, operation):
    service, note, _ = custom_env
    with tenant_context("t1"):
        await service.grant(ResourcePrincipal(OWNER), grant_data(note, role="reviewer"))
        target = await service.grant(
            ResourcePrincipal(OWNER), grant_data(note, READER, "validator")
        )
        who = ResourcePrincipal(MANAGER)
        with pytest.raises(SharingError) as exc:
            if operation == "grant":
                await service.grant(who, grant_data(note, OTHER))
            elif operation == "list":
                await service.for_resource(who, TYPE, str(note.id))
            else:
                await service.revoke(who, target.id)
        assert exc.value.status_code == 403


@pytest.mark.parametrize("role", [ACTION_VIEW, ACTION_EDIT, "validate", "unknown"])
async def test_grant_accepts_only_declared_role_keys(custom_env, role):
    service, note, _ = custom_env
    with tenant_context("t1"), pytest.raises(SharingError) as exc:
        await service.grant(ResourcePrincipal(OWNER), grant_data(note, role=role))
    assert exc.value.status_code == 422


async def test_custom_roles_expire_and_remain_tenant_scoped(custom_env):
    service, note, resource = custom_env
    who = ResourcePrincipal(MANAGER)
    with tenant_context("t1"):
        share = await service.grant(ResourcePrincipal(OWNER), grant_data(note))
    with tenant_context("t2"), pytest.raises(SharingError) as exc:
        await service.for_resource(who, TYPE, str(note.id))
    assert exc.value.status_code == 404
    with tenant_context("t1"):
        share.expires_at = utcnow() - timedelta(seconds=1)
        await service.db.flush()
        assert await visible(service, resource, MANAGER, ACTION_VIEW) == []
        with pytest.raises(SharingError) as exc:
            await service.for_resource(who, TYPE, str(note.id))
        assert exc.value.status_code == 404


@pytest.mark.parametrize("custom_env", [{}], indirect=True)
async def test_empty_mapping_refuses_default_grants(custom_env):
    service, note, _ = custom_env
    with tenant_context("t1"), pytest.raises(SharingError) as exc:
        await service.grant(ResourcePrincipal(OWNER), grant_data(note, role=ACTION_VIEW))
    assert exc.value.status_code == 422


@pytest.mark.parametrize("subset", [(ACTION_VIEW,), (ACTION_EDIT,), ()])
async def test_legacy_subset_still_controls_grants(custom_env, subset):
    service, note, _ = custom_env
    with pytest.warns(DeprecationWarning):
        resource = declaration(shareable_actions=subset)
    registry = ResourceTypeRegistry()
    registry.register(resource)
    service.registry = registry
    with tenant_context("t1"):
        for role in (ACTION_VIEW, ACTION_EDIT):
            if role in subset:
                share = await service.grant(ResourcePrincipal(OWNER), grant_data(note, role=role))
                assert share.role == role
            else:
                with pytest.raises(SharingError) as exc:
                    await service.grant(ResourcePrincipal(OWNER), grant_data(note, role=role))
                assert exc.value.status_code == 422


def test_explicit_roles_take_precedence_over_legacy_subset():
    with pytest.warns(DeprecationWarning):
        resource = declaration(share_roles=ROLES, shareable_actions=(ACTION_VIEW,))
    assert resource.share_roles == ROLES


@pytest.mark.parametrize("role", ["Manager", "x" * 33, "has-dash", "", "manager\n"])
def test_role_ids_must_fit_the_share_column(role):
    # A role the 32-character ``role`` column can't store would only fail at grant time.
    with pytest.raises(ResourceTypeError, match="lowercase identifier"):
        ResourceTypeRegistry().register(declaration(share_roles={role: (ACTION_VIEW,)}))


def test_core_role_pattern_matches_share_column_width():
    # ``simple_module_core.resources._ROLE_ID`` hard-codes the width (core can't import sharing).
    assert ROLE_MAX == 32
