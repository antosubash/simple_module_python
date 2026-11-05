"""``api_tokens`` under Keycloak: service keys work, personal tokens are refused.

``Users`` is only an ordering hint for ``api_tokens`` (GH #501), so a strict
(non-development) Keycloak boot keeps it. A service key needs no account; a
personal token needs its owner's roles, which live in the IdP, so it is
refused rather than acting with none.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from api_tokens.constants import TokenKind
from api_tokens.models import ApiToken
from api_tokens.resolver import SERVICE_PRINCIPAL_PREFIX, resolve_api_token
from api_tokens.tokens import generate
from auth.contracts.tokens import AUTH_KIND_SERVICE
from keycloak.models import KeycloakUserCache
from keycloak_test_modules import keycloak_modules_enabled
from simple_module_core.user_directory import get_user_directory
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings
from simple_module_test._schema import _create_all_tables
from starlette.requests import Request


def _app():
    return create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment="testing",
            secret_key="test-secret-key",
            multi_tenant=False,
            auth_provider="keycloak",
            modules_enabled=keycloak_modules_enabled(),
        )
    )


def _request(app, credential: str) -> Request:
    headers = [(b"authorization", f"Bearer {credential}".encode())]
    return Request({"type": "http", "app": app, "headers": headers, "method": "GET", "path": "/"})


async def _issue(app, kind: TokenKind, **kw) -> str:
    issued = generate(kind)
    async with app.state.sm.db.session_factory() as db:
        db.add(
            ApiToken(
                kind=kind,
                name=f"{kind}-key",
                prefix=issued.prefix,
                token_hash=issued.token_hash,
                scopes=["feature_flags.view"],
                expires_at=datetime.now(UTC) + timedelta(days=1),
                **kw,
            )
        )
        await db.commit()
    return issued.plaintext


async def test_api_tokens_boot_strictly_with_service_keys_only():
    app = _app()
    assert "ApiTokens" in {m.meta.name for m in app.state.sm.modules}
    await _create_all_tables(app.state.sm.db.engine)
    try:
        async with app.state.sm.db.session_factory() as db:
            owner = KeycloakUserCache(keycloak_sub="sub-owner", email="owner@example.com")
            db.add(owner)
            await db.commit()
            owner_id = owner.id

        service = await _issue(app, TokenKind.SERVICE, roles=["reader"])
        principal = await resolve_api_token(_request(app, service))
        assert principal is not None
        assert principal.auth_kind == AUTH_KIND_SERVICE
        assert principal.id.startswith(SERVICE_PRINCIPAL_PREFIX)
        assert principal.roles == ["reader"]

        # The owner is known to the directory; only their roles are not.
        async with app.state.sm.db.session_factory() as db:
            known = await get_user_directory(app).get_many(db, [str(owner_id)], with_roles=True)
        assert known[str(owner_id)].roles is None
        personal = await _issue(app, TokenKind.PERSONAL, owner_user_id=owner_id)
        assert await resolve_api_token(_request(app, personal)) is None
    finally:
        await app.state.sm.db.engine.dispose()
