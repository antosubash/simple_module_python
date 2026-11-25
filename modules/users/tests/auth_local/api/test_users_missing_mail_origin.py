"""An unset email origin must not expose whether an account exists."""

from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi_users.db import BaseUserDatabase
from simple_module_hosting.config.host_settings import HostSettings
from simple_module_hosting.pipeline._forwarded_host import ForwardedHostMiddleware
from users.accounts.db_adapter import get_user_db
from users.auth_local.rate_limit import ThroughputLimiter
from users.core.settings import UsersSettings
from users.core.startup import _build_mailer
from users.core.token_secrets import resolve_token_secrets
from users.models import User
from users.module import UsersModule
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


class _AccountLookup(BaseUserDatabase[User, UUID]):
    """Replace only DB I/O; router, manager, token generation and mailer stay real."""

    def __init__(self, user: User):
        self.user = user

    async def get_by_email(self, email: str) -> User | None:
        return self.user if email == self.user.email else None


@pytest.mark.parametrize("endpoint", ["forgot-password", "request-verify-token"])
@pytest.mark.parametrize(
    "request_origin, allowlist, headers, proxy, host_origin, users_origin, expected",
    [
        ("https://app.example", [], {}, None, "", "", None),
        (
            "https://app.example:8443",
            ["app.example:8443"],
            {},
            None,
            "",
            "",
            "https://app.example:8443",
        ),
        ("https://app.example", ["app.example"], {"host": "evil.example"}, None, "", "", None),
        ("https://app.example", ["app.example"], {"host": "evil.example/path"}, None, "", "", None),
        (
            "https://internal.example",
            ["app.example"],
            {"x-forwarded-host": "app.example"},
            "10.0.0.1",
            "",
            "",
            None,
        ),
        (
            "http://internal.example",
            ["app.example"],
            {"x-forwarded-host": "app.example", "x-forwarded-proto": "https"},
            "127.0.0.1",
            "",
            "",
            "https://app.example",
        ),
        ("https://one.app.example", ["*.app.example"], {}, None, "", "", "https://one.app.example"),
        ("http://localhost:8000", ["localhost"], {}, None, "", "", "http://localhost:8000"),
        ("http://app.example", ["app.example"], {}, None, "", "", None),
        ("http://app.example", ["app.example"], {}, "10.0.0.1", "", "", None),
        (
            "http://internal.example",
            ["app.example"],
            {
                "x-forwarded-host": "app.example",
                "x-forwarded-proto": "http",
                "x-forwarded-for": "203.0.113.10",
            },
            "127.0.0.1",
            "",
            "",
            "http://app.example",
        ),
        (
            "https://app.example",
            ["app.example"],
            {},
            None,
            "https://host.example",
            "",
            "https://host.example",
        ),
        (
            "https://app.example",
            ["app.example"],
            {},
            None,
            "https://host.example",
            "https://users.example",
            "https://users.example",
        ),
    ],
)
async def test_account_mail_origin_preserves_public_response(
    captured_mail,
    caplog,
    endpoint,
    request_origin,
    allowlist,
    headers,
    proxy,
    host_origin,
    users_origin,
    expected,
):
    app = FastAPI()
    app.state.host = SimpleNamespace(
        settings=HostSettings(
            _env_file=None, public_base_url=host_origin, forwarded_host_allowlist=allowlist
        )
    )
    if proxy:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=proxy)
        app.add_middleware(ForwardedHostMiddleware, trusted_hosts=proxy, allowlist=allowlist)
    app.state.users = SimpleNamespace(
        settings=UsersSettings(
            base_url=users_origin,
        ),
        auth_throughput_limiter=ThroughputLimiter(),
        token_secrets=resolve_token_secrets("test-secret-key"),
    )
    _build_mailer(app, app.state.users, app.state.users.settings)
    accounts = _AccountLookup(
        User(
            email="existing@example.com",
            hashed_password="unused-password-hash",
            is_active=True,
            is_verified=False,
        )
    )

    async def user_db():
        yield accounts

    app.dependency_overrides[get_user_db] = user_db
    api = APIRouter(prefix="/api/users")
    UsersModule().register_routes(api, APIRouter())
    app.include_router(api)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=request_origin, headers=headers
    ) as client:
        unknown = await client.post(
            f"/api/users/auth/{endpoint}", json={"email": "unknown@example.com"}
        )
        existing = await client.post(
            f"/api/users/auth/{endpoint}", json={"email": "existing@example.com"}
        )

    assert unknown.status_code == 202
    assert existing.status_code == unknown.status_code
    assert existing.content == unknown.content
    errors = [record for record in caplog.records if record.name == "users.mailer.templated"]
    if expected:
        assert len(captured_mail.messages) == 1
        path = "reset-password" if endpoint == "forgot-password" else "verify"
        assert f"{expected}/users/{path}?token=" in captured_mail.messages[0].text
        assert not errors
        return

    assert not captured_mail.messages
    assert len(errors) == 1
    assert errors[0].levelname == "ERROR"
    assert "host.public_base_url" in errors[0].message
    assert "SM_PUBLIC_BASE_URL" in errors[0].message
