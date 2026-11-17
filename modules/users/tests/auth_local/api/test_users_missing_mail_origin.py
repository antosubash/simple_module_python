"""An unset email origin must not expose whether an account exists."""

from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi_users.db import BaseUserDatabase
from simple_module_hosting.host_settings import HostSettings
from users.accounts.db_adapter import get_user_db
from users.auth_local.rate_limit import ThroughputLimiter
from users.core.settings import UsersSettings
from users.core.startup import _build_mailer
from users.models import User
from users.module import UsersModule


class _AccountLookup(BaseUserDatabase[User, UUID]):
    """Replace only DB I/O; router, manager, token generation and mailer stay real."""

    def __init__(self, user: User):
        self.user = user

    async def get_by_email(self, email: str) -> User | None:
        return self.user if email == self.user.email else None


@pytest.mark.parametrize("endpoint", ["forgot-password", "request-verify-token"])
async def test_missing_mail_origin_preserves_public_response(captured_mail, caplog, endpoint):
    app = FastAPI()
    app.state.host = SimpleNamespace(settings=HostSettings(_env_file=None, public_base_url=""))
    app.state.users = SimpleNamespace(
        settings=UsersSettings(
            base_url="",
            reset_password_token_secret="test-reset-secret-32-bytes-xxxxx",
            verification_token_secret="test-verify-secret-32-bytes-xxxxx",
        ),
        auth_throughput_limiter=ThroughputLimiter(),
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
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        unknown = await client.post(
            f"/api/users/auth/{endpoint}", json={"email": "unknown@example.com"}
        )
        existing = await client.post(
            f"/api/users/auth/{endpoint}", json={"email": "existing@example.com"}
        )

    assert unknown.status_code == 202
    assert existing.status_code == unknown.status_code
    assert existing.content == unknown.content
    assert not captured_mail.messages
    errors = [record for record in caplog.records if record.name == "users.mailer.templated"]
    assert len(errors) == 1
    assert errors[0].levelname == "ERROR"
    assert "host.public_base_url" in errors[0].message
    assert "SM_PUBLIC_BASE_URL" in errors[0].message
