"""Who may grant which roles (#624): full admin, an admin's scoped token, delegates."""

import pytest
from auth.contracts.schemas import UserContext
from users.admin.safety import check_role_assignment
from users.exceptions import AdminPermissionError


def _actor(roles, scopes=None):
    return UserContext(id="a", email="a@x", name="a", roles=roles, scopes=scopes)


def test_full_admin_grants_admin():
    check_role_assignment(_actor(["admin"]), ["admin", "editor"])


def test_admin_scoped_token_grants_ordinary_roles_but_not_admin():
    token = _actor(["admin"], scopes=["users.manage"])
    check_role_assignment(token, ["editor"])
    with pytest.raises(AdminPermissionError):
        check_role_assignment(token, ["admin"])


def test_delegate_grants_only_roles_it_holds():
    helpdesk = _actor(["helpdesk", "editor"])
    check_role_assignment(helpdesk, ["editor"])
    with pytest.raises(AdminPermissionError):
        check_role_assignment(helpdesk, ["admin"])
    with pytest.raises(AdminPermissionError):
        check_role_assignment(helpdesk, ["billing"])


def test_trusted_in_process_caller_is_unrestricted():
    check_role_assignment(None, ["admin"])
