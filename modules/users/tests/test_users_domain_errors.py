"""Domain failures remain usable outside HTTP request handlers."""

import uuid

from fastapi import HTTPException
from users.auth_local.lockout import too_many_attempts
from users.exceptions import UserNotFoundError


def test_lockout_is_a_domain_error():
    error = too_many_attempts(0)
    assert not isinstance(error, HTTPException)
    assert error.retry_after == 1


def test_user_errors_share_a_module_base():
    from users.exceptions import UsersError

    assert isinstance(UserNotFoundError(uuid.uuid4()), UsersError)


async def test_lockout_http_mapping_preserves_body_and_retry_after():
    import httpx
    from fastapi import FastAPI
    from users.module import UsersModule

    app = FastAPI()
    UsersModule().register_exception_handlers(app)

    @app.get("/locked")
    async def locked():
        raise too_many_attempts(0)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/locked")
    assert response.status_code == 429
    assert response.content == '{"detail":"Too many attempts — try again later"}'.encode()
    assert response.headers["Retry-After"] == "1"
