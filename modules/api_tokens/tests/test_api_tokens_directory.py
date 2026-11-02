"""Token owners are read through the user directory (GH #501)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from api_tokens.constants import PERM_USE, TokenKind
from api_tokens.models import ApiToken
from api_tokens.resolver import _personal
from api_tokens.service import ApiTokenService
from auth.contracts.tokens import AUTH_KIND_PAT
from simple_module_core.user_directory import DirectoryUser, NullUserDirectory

_OWNER = uuid.uuid4()


class _Directory(NullUserDirectory):
    def __init__(self, user: DirectoryUser | None) -> None:
        self.user = user
        self.asked_roles: list[bool] = []

    async def get_many(self, db, ids, *, with_roles=False):
        self.asked_roles.append(with_roles)
        return {self.user.id: self.user} if self.user and self.user.id in ids else {}


def _token(**kw) -> ApiToken:
    return ApiToken(
        kind=TokenKind.PERSONAL,
        name="t",
        prefix="smpat_x",
        token_hash="h",
        owner_user_id=_OWNER,
        scopes=["feature_flags.view"],
        expires_at=datetime.now(UTC) + timedelta(days=1),
        tenant_id="default",
        **kw,
    )


def _owner(**kw) -> DirectoryUser:
    return DirectoryUser(id=str(_OWNER), email="o@example.com", **kw)


class TestPersonalTokenResolution:
    async def test_an_active_owner_with_known_roles_authenticates(self):
        directory = _Directory(_owner(full_name="Owen", roles=("editor",)))
        principal = await _personal(None, directory, _token())
        assert principal is not None
        assert (principal.id, principal.name, principal.roles) == (str(_OWNER), "Owen", ["editor"])
        assert principal.auth_kind == AUTH_KIND_PAT
        assert principal.scopes == ["feature_flags.view"]
        assert principal.required_permission == PERM_USE
        assert principal.tenant_id == "default"
        assert directory.asked_roles == [True]

    async def test_unknown_roles_refuse_the_token(self):
        """Keycloak keeps roles in the IdP: refuse rather than act with none."""
        assert await _personal(None, _Directory(_owner(roles=None)), _token()) is None

    async def test_an_inactive_or_missing_owner_refuses(self):
        inactive = _Directory(_owner(roles=(), is_active=False))
        assert await _personal(None, inactive, _token()) is None
        assert await _personal(None, _Directory(None), _token()) is None


class TestServiceOwners:
    async def test_usable_account_needs_known_roles(self):
        known = ApiTokenService(None, _Directory(_owner(roles=())))
        unknown = ApiTokenService(None, _Directory(_owner(roles=None)))
        assert await known.has_usable_account(_OWNER) is True
        assert await unknown.has_usable_account(_OWNER) is False

    async def test_owner_emails(self):
        service = ApiTokenService(None, _Directory(_owner()))
        other = _token()
        other.owner_user_id = uuid.uuid4()
        emails = await service.owner_emails([_token(), other])
        assert emails == {_OWNER: "o@example.com"}
