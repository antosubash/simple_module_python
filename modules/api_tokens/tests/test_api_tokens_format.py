"""Token format, hashing, and the pure permission helpers the cap is built from."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

from api_tokens.constants import SECRET_LENGTH, TokenKind
from api_tokens.tokens import base62, display_prefix, generate, hash_token, is_well_formed
from auth.contracts.schemas import UserContext
from auth.contracts.tokens import is_api_token
from simple_module_core.permissions import is_admin_principal
from simple_module_hosting.permissions import apply_scope_cap


class TestTokenFormat:
    def test_personal_token_shape(self):
        new = generate(TokenKind.PERSONAL)
        assert new.plaintext.startswith("smpat_")
        assert len(new.plaintext) == len("smpat_") + SECRET_LENGTH
        assert is_well_formed(new.plaintext)
        assert is_api_token(new.plaintext)

    def test_service_key_shape(self):
        new = generate(TokenKind.SERVICE)
        assert new.plaintext.startswith("smsk_")
        assert is_well_formed(new.plaintext)

    def test_only_the_sha256_is_kept(self):
        new = generate(TokenKind.PERSONAL)
        assert new.token_hash == hashlib.sha256(new.plaintext.encode()).hexdigest()
        assert new.token_hash == hash_token(new.plaintext)
        assert new.plaintext not in new.token_hash

    def test_display_prefix_is_kind_plus_eight(self):
        new = generate(TokenKind.PERSONAL)
        assert new.prefix == new.plaintext[: len("smpat_") + 8]
        assert display_prefix("smsk_" + "a" * SECRET_LENGTH) == "smsk_aaaaaaaa"

    def test_tokens_are_unique(self):
        assert len({generate(TokenKind.PERSONAL).plaintext for _ in range(200)}) == 200

    def test_base62_pads_to_fixed_width(self):
        assert base62(b"\x00" * 32) == "0" * SECRET_LENGTH
        assert len(base62(b"\xff" * 32)) == SECRET_LENGTH

    def test_malformed_values_are_rejected_before_any_lookup(self):
        good = generate(TokenKind.PERSONAL).plaintext
        for bad in (
            "",
            "smpat_",
            good[:-1],
            good + "x",
            good.replace("smpat_", "smxx_"),
            "smpat_" + "-" * SECRET_LENGTH,
            "eyJhbGciOiJIUzI1NiJ9.e30.x",
        ):
            assert not is_well_formed(bad), bad


class TestUserContextFields:
    def test_defaults_are_an_uncapped_session(self):
        ctx = UserContext(id="1", email="a@b", name="A")
        assert ctx.auth_kind == "session"
        assert ctx.scopes is None
        assert not ctx.is_scoped

    def test_session_dict_round_trip_keeps_kind_and_scopes(self):
        ctx = UserContext(id="1", email="a@b", name="A", auth_kind="pat", scopes=["x.read"])
        back = UserContext.from_session_dict(ctx.to_session_dict())
        assert back is not None
        assert back.auth_kind == "pat"
        assert back.scopes == ["x.read"]

    def test_old_cookie_without_the_fields_is_a_session(self):
        back = UserContext.from_session_dict({"id": "1", "email": "a@b", "name": "A"})
        assert back is not None
        assert back.auth_kind == "session"
        assert back.scopes is None

    def test_from_user_threads_kind_and_scopes(self):
        user = SimpleNamespace(id="u", email="a@b", full_name=None, roles=[])
        ctx = UserContext.from_user(user, auth_kind="pat", scopes=["x.read"])
        assert (ctx.auth_kind, ctx.scopes) == ("pat", ["x.read"])


class TestScopeCap:
    def test_no_scopes_means_no_cap(self):
        user = SimpleNamespace(scopes=None)
        assert apply_scope_cap({"a", "b"}, user) == {"a", "b"}

    def test_intersection_with_held(self):
        user = SimpleNamespace(scopes=["a", "c"])
        assert apply_scope_cap({"a", "b"}, user) == {"a"}

    def test_wildcard_expands_to_the_scope_list_only(self):
        user = SimpleNamespace(scopes=["a", "c"])
        assert apply_scope_cap({"*"}, user) == {"a", "c"}

    def test_a_wildcard_scope_is_never_honoured(self):
        user = SimpleNamespace(scopes=["*", "a"])
        assert apply_scope_cap({"*"}, user) == {"a"}
        assert apply_scope_cap({"b"}, SimpleNamespace(scopes=["*"])) == set()

    def test_empty_scope_list_caps_to_nothing(self):
        assert apply_scope_cap({"*"}, SimpleNamespace(scopes=[])) == set()

    def test_admin_principal_excludes_tokens(self):
        assert is_admin_principal(SimpleNamespace(roles=["admin"], scopes=None))
        assert not is_admin_principal(SimpleNamespace(roles=["admin"], scopes=["a"]))
        assert not is_admin_principal(SimpleNamespace(roles=["user"], scopes=None))
        assert not is_admin_principal(None)
