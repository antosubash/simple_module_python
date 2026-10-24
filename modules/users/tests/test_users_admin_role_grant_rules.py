"""Who may grant which roles (#624): compared by effective permissions, not role names."""

import pytest
from auth.contracts.schemas import UserContext
from simple_module_hosting.permissions import apply_scope_cap, resolve_permissions
from users.admin.safety import check_role_assignment
from users.exceptions import AdminPermissionError

ROLE_MAP = {
    "admin": ["*"],
    "helpdesk": ["users.manage"],
    "editor": ["pages.edit"],
    "billing": ["billing.manage"],
    "files": ["files.delete"],
    "empty": [],
}


def _check(roles, wanted, scopes=None):
    actor = UserContext(id="a", email="a@x", name="a", roles=roles, scopes=scopes)
    held = apply_scope_cap(resolve_permissions(roles, ROLE_MAP), actor)
    check_role_assignment(actor, wanted, held, ROLE_MAP)


def test_full_admin_grants_admin():
    _check(["admin"], ["admin", "editor"])


def test_admin_scoped_token_cannot_grant_admin():
    with pytest.raises(AdminPermissionError):
        _check(["admin"], ["admin"], scopes=["users.manage"])


def test_admin_scoped_token_grants_only_roles_within_its_scopes():
    _check(["admin"], ["helpdesk", "empty"], scopes=["users.manage"])
    with pytest.raises(AdminPermissionError):
        _check(["admin"], ["files"], scopes=["users.manage"])


def test_delegate_grants_roles_its_permissions_cover():
    _check(["helpdesk", "editor"], ["editor", "empty"])
    for wanted in (["admin"], ["billing"], ["files"]):
        with pytest.raises(AdminPermissionError):
            _check(["helpdesk", "editor"], wanted)


def test_delegate_holding_equivalent_permissions_via_another_role_may_grant():
    ROLE_MAP["twin"] = ["pages.edit"]
    try:
        _check(["editor"], ["twin"])
    finally:
        del ROLE_MAP["twin"]


def test_trusted_in_process_caller_is_unrestricted():
    check_role_assignment(None, ["admin"], set(), ROLE_MAP)
