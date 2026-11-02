"""Build an OIDC-selected app; mock only the external identity provider."""

import json

import httpx
import pytest
from jwt.algorithms import RSAAlgorithm
from oidc.settings import OidcSettings
from oidc_flow_helpers import _AUDIENCE, _ISSUER, _KID, _PRIVATE_KEY
from simple_module_core.discovery import discover_modules
from simple_module_db.base import all_module_bases
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.migrations import resolve_head_revisions
from simple_module_hosting.settings import Settings
from sqlalchemy import text


@pytest.fixture
async def oidc_app(httpx_mock):
    # Explicitly boot without Settings UI or Users-dependent modules.
    modules = [
        m.meta.name
        for m in discover_modules()
        if m.meta.name not in {"Users", "Settings", "Keycloak"}
        and "Users" not in m.meta.depends_on
        and "Settings" not in m.meta.depends_on
    ]
    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment="testing",
            secret_key="test-secret-key",
            multi_tenant=False,
            auth_provider="oidc",
            modules_enabled=modules,
        )
    )
    async with app.state.sm.db.engine.begin() as conn:

        def create(sync):
            for base in all_module_bases:
                if "oidc_user_cache" not in base.metadata.tables:
                    base.metadata.create_all(sync)

        await conn.run_sync(create)
        from alembic.config import Config
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from alembic.script import ScriptDirectory

        revision = ScriptDirectory.from_config(Config("host/alembic.ini")).get_revision("oidc@head")

        def migrate(sync):
            with Operations.context(MigrationContext.configure(sync)):
                revision.module.upgrade()

        await conn.run_sync(migrate)
        await conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        )
        for head in resolve_head_revisions():
            await conn.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": head})

    # Settings hydration restores defaults; supply DB-backed values before startup.
    oidc_settings = OidcSettings(
        provider="entra",
        tenant_id="test-tenant",
        client_id=_AUDIENCE,
        client_secret="secret",
        api_audience="api",
    )
    from simple_module_db.stored_settings import Setting

    async with app.state.sm.db.session_factory() as db:
        for name, value in oidc_settings.model_dump().items():
            db.add(Setting(key=f"oidc.{name}", value=json.dumps(value), value_type="json"))
        await db.commit()

    httpx_mock.add_response(
        url=oidc_settings.discovery_url,
        json={
            "issuer": _ISSUER,
            "authorization_endpoint": "https://idp/authorize",
            "token_endpoint": "https://idp/token",
            "jwks_uri": "https://idp/keys",
            "end_session_endpoint": "https://idp/logout",
        },
        is_reusable=True,
    )
    jwk = json.loads(RSAAlgorithm.to_jwk(_PRIVATE_KEY.public_key()))
    jwk.update(kid=_KID, use="sig")
    httpx_mock.add_response(
        url="https://idp/keys", json={"keys": [jwk]}, is_reusable=True, is_optional=True
    )
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def flow_client(oidc_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=oidc_app), base_url="http://testserver"
    ) as client:
        yield client
