"""Subject registries are isolated, and policy membership stays in SQL (#963)."""

from unittest.mock import AsyncMock

import pytest
from _sharing_support import NOTE_TYPE, FakeDirectory, SharingTestNote, register_note_type
from sharing.contracts import SubjectProvider, SubjectRegistry
from sharing.contracts.schemas import ShareGrant
from sharing.core.service import SharingError, SharingService
from sharing.models import ResourceShare
from simple_module_core.access.resources import ResourcePrincipal, ResourceTypeRegistry
from simple_module_core.access.tenancy import TenantRole, tenant_role
from simple_module_db.tenancy import tenant_context
from sqlalchemy import column


def team_provider():
    return SubjectProvider(
        name="team",
        label_key="teams.subject_type",
        validate=AsyncMock(return_value="one"),
        candidates=AsyncMock(return_value=[]),
        labels=AsyncMock(return_value={"one": "One"}),
        membership=lambda principal, subject_id: subject_id.in_(["one"]),
    )


def test_registration_rejects_duplicates_and_invalid_names():
    registry = SubjectRegistry()
    provider = team_provider()
    registry.register(provider)
    assert registry.get("team") is provider
    assert SubjectRegistry().get("team") is None
    with pytest.raises(ValueError):
        registry.register(provider)
    for name in ("", "Team", "a" * 17, "team.id"):
        with pytest.raises(ValueError):
            registry.register(SubjectProvider(**{**provider.__dict__, "name": name}))


def test_role_membership_is_tenant_bound_and_not_inferred_from_permissions():
    from sharing.core.subjects import default_subject_registry

    provider = default_subject_registry().get("tenant_role")
    who = ResourcePrincipal(
        "member", roles=frozenset({tenant_role(TenantRole.MEMBER)}), tenant_id="a"
    )
    with tenant_context("a"):
        clause = provider.membership(who, column("subject_id"))
        assert "member" in str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert (
            str(provider.membership(ResourcePrincipal("u", frozenset({"*"})), column("id")))
            == "false"
        )
    with tenant_context("b"):
        assert str(provider.membership(who, column("id"))) == "false"


async def test_unregistered_subject_is_refused_before_writing():
    registry = ResourceTypeRegistry()
    register_note_type(registry)
    db = AsyncMock()
    service = SharingService(db, registry, FakeDirectory("friend"))
    service._authorize = AsyncMock(return_value=SharingTestNote(owner_id="owner"))
    with pytest.raises(SharingError) as error:
        await service.grant(
            ResourcePrincipal("owner"),
            ShareGrant(
                resource_type=NOTE_TYPE,
                resource_id="note",
                subject_id="one",
                subject_type="unknown",
            ),
        )
    assert error.value.status_code == 422
    db.flush.assert_not_awaited()


def test_sharing_registers_builtins_for_each_host_and_worker():
    from sharing.contracts import get_subject_registry
    from sharing.module import SharingModule
    from simple_module_core.access.principals import PrincipalRegistry

    first, second = PrincipalRegistry(), PrincipalRegistry()
    SharingModule().register_principal_builder(first)
    SharingModule().register_principal_builder(second)
    one = get_subject_registry(first)
    assert {p.name for p in one.all()} == {"user", "tenant_role"}
    one.register(team_provider())
    assert get_subject_registry(first) is one
    assert get_subject_registry(second).get("team") is None


async def test_provider_validation_and_batched_labels_do_not_resolve_other_subjects_as_users():
    from sharing.contracts.subjects import SUBJECTS_KEY
    from sharing.core.audience import OpenAudience
    from sharing.core.subjects import default_subject_registry
    from sharing.web.present import present_shares

    provider = team_provider()
    subjects = default_subject_registry()
    subjects.register(provider)
    directory = FakeDirectory("owner")
    directory.get_many = AsyncMock(wraps=directory.get_many)
    who = ResourcePrincipal("owner", context={SUBJECTS_KEY: subjects})
    rows = [
        ResourceShare(
            resource_type=NOTE_TYPE,
            resource_id=str(i),
            subject_type="team",
            subject_id="one",
            role="view",
            granted_by="owner",
        )
        for i in range(5)
    ]
    out = await present_shares(directory, AsyncMock(), rows, OpenAudience(), who)
    assert all(s.subject_label == "One" for s in out)
    provider.labels.assert_awaited_once()
    assert provider.labels.await_args.args[1] == {"one"}
    directory.get_many.assert_awaited_once()
    assert set(directory.get_many.await_args.args[1]) == {"owner"}
    foreign = ResourceShare(
        resource_type=NOTE_TYPE,
        resource_id="n",
        subject_type="unknown",
        subject_id="owner",
        role="view",
        granted_by="owner",
    )
    (out,) = await present_shares(directory, AsyncMock(), [foreign], OpenAudience(), who)
    assert out.subject_label is None


async def test_user_provider_preserves_canonical_directory_ids():
    from sharing.contracts import SubjectContext
    from sharing.core.audience import OpenAudience
    from sharing.core.subjects import default_subject_registry
    from simple_module_core.access.user_directory import DirectoryUser

    canonical = "12345678-1234-1234-1234-123456789abc"
    alias = canonical.upper()
    directory = FakeDirectory()
    directory.users[alias] = DirectoryUser(id=canonical, email="friend@test")
    ctx = SubjectContext(AsyncMock(), directory, OpenAudience(), ResourcePrincipal("owner"))
    provider = default_subject_registry().get("user")
    assert await provider.validate(ctx, alias) == canonical
