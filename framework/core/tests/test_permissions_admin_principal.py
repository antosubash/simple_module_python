"""``is_admin_principal``: the role-only admin gate that tokens never pass."""

from __future__ import annotations

from types import SimpleNamespace

from simple_module_core.permissions import is_admin_principal


def test_admin_session_passes() -> None:
    assert is_admin_principal(SimpleNamespace(roles=["admin"], scopes=None))
    assert is_admin_principal(SimpleNamespace(roles=["admin"]))  # no scopes attribute


def test_admin_token_never_passes_even_with_empty_scopes() -> None:
    assert not is_admin_principal(SimpleNamespace(roles=["admin"], scopes=["x.read"]))
    assert not is_admin_principal(SimpleNamespace(roles=["admin"], scopes=[]))


def test_non_admin_and_anonymous_fail() -> None:
    assert not is_admin_principal(SimpleNamespace(roles=["user"], scopes=None))
    assert not is_admin_principal(SimpleNamespace(roles=None, scopes=None))
    assert not is_admin_principal(None)
