"""Principal composition is pure and never widens untrusted grants or scope caps."""

from types import SimpleNamespace

import pytest
from simple_module_core.access.principal_permissions import compose_principal
from simple_module_core.access.resources import ResourcePrincipal


@pytest.mark.parametrize(
    "roles,scopes,required,want",
    [
        (
            ["reader", "tenant:member"],
            None,
            None,
            {"test.role", "test.member", "test.claim", "test.direct"},
        ),
        (
            ["reader", "tenant:member"],
            ["test.member", "test.direct", "*"],
            "test.role",
            {"test.member", "test.direct"},
        ),
        ([], None, "test.role", None),
        (["admin"], ["test.direct", "*"], None, {"test.direct"}),
        (["admin"], None, None, {"*", "test.claim", "test.direct"}),
    ],
)
def test_loaded_account_roles_membership_and_grants(roles, scopes, required, want):
    user = SimpleNamespace(
        id="u1",
        roles=roles,
        permissions=["test.claim", "*"],
        scopes=scopes,
        required_permission=required,
    )
    role_map = {"reader": ["test.role"], "tenant:member": ["test.member"], "admin": ["*"]}
    who = compose_principal(user, role_map, ["test.direct", "*"])
    assert who == (
        None if want is None else ResourcePrincipal("u1", frozenset(want), roles=frozenset(roles))
    )


def test_principal_carries_tenant_roles_separately_from_capped_permissions():
    user = SimpleNamespace(id="u", roles=["tenant:member"], tenant_id="a", scopes=[])
    who = compose_principal(user, {"tenant:member": ["sharing.share"]}, [])
    assert who.permissions == frozenset()
    assert who.roles == frozenset({"tenant:member"})
    assert who.tenant_id == "a"
