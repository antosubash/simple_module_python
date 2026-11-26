"""Run the real ``smdev`` CLI against the in-process dev host.

The ``app`` fixture owns the event loop and the DB engine, so the (synchronous)
CLI runs in a worker thread and every HTTP request is handed back to the test
loop through :class:`LoopBridgeTransport`.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from click.testing import CliRunner, Result
from simple_module_test.web.tenant_client import create_user, session_client
from smdev_cli import make_cli

BASE_URL = "http://127.0.0.1"
CSRF = "csrf-test-token"
PAT_URL = "/api/api_tokens/tokens/"
ENV_NAME = "local"


async def make_admin(app: Any, email: str) -> str:
    from users.core.bootstrap import create_admin

    async with app.state.sm.db.session_factory() as session:
        result = await create_admin(session, email=email, password="pw-123456", full_name="Admin")
        return str(result.user.id)


async def join_tenant(app: Any, user_id: str, email: str, tenant_id: str | None) -> str:
    """Make *user_id* an owner of a new tenant (or of *tenant_id*); return its id."""
    from simple_module_core.access.tenancy import TenantRole
    from tenants.models import Membership, Tenant
    from tenants.resolution.resolver import forget

    async with app.state.sm.db.session_factory() as session:
        if tenant_id is None:
            tenant = Tenant(slug=f"t-{uuid.uuid4().hex[:12]}", name="Test Org")
            session.add(tenant)
            await session.flush()
            tenant_id = tenant.id
        session.add(
            Membership(tenant_id=tenant_id, user_id=user_id, role=TenantRole.OWNER, email=email)
        )
        await session.commit()
    forget(user_id)  # the resolver caches memberships per user
    return tenant_id


async def create_pat(client: httpx.AsyncClient, scopes: list[str]) -> dict:
    """POST a personal token (the pattern of the api_tokens tests); return the body."""
    resp = await client.post(
        PAT_URL,
        json={"name": "smdev", "scopes": scopes, "expires_in_days": 30},
        headers={"X-CSRF-Token": CSRF},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class FakeKeyring:
    """In-memory keyring so tests never touch the developer's credential store."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.data[(service, username)]


class LoopBridgeTransport(httpx.BaseTransport):
    """A sync transport that serves each request from ``app`` on the test loop."""

    def __init__(self, app: Any, loop: asyncio.AbstractEventLoop) -> None:
        self._asgi = httpx.ASGITransport(app=app)
        self._loop = loop
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        request.read()
        future = asyncio.run_coroutine_threadsafe(self._serve(request), self._loop)
        return future.result()

    async def _serve(self, request: httpx.Request) -> httpx.Response:
        response = await self._asgi.handle_async_request(request)
        # Raw bytes: the Response below decodes Content-Encoding itself.
        body = b"".join([chunk async for chunk in response.aiter_raw()])
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=body,
            request=request,
        )


@dataclass
class Smdev:
    """Invoke the CLI; ``transport.requests`` records what reached the app."""

    app: Any
    loop: asyncio.AbstractEventLoop
    transport: LoopBridgeTransport
    keyring: FakeKeyring

    async def run(self, *args: str, input: str | None = None) -> Result:
        cli = make_cli(transport=self.transport, keyring_backend=self.keyring)
        return await asyncio.to_thread(CliRunner().invoke, cli, list(args), input=input)

    async def token_for(self, actor: Any, scopes: list[str] | None = None) -> str:
        """A PAT for *actor*; default: every registered permission (the admin holds them all).

        Admin-managing-user checks compare the target's permissions to the token's
        capped ones, so a narrow scope list would be refused with a 403.
        """
        if scopes is None:
            scopes = sorted(p for p in self.app.state.sm.permissions.all_permissions if p != "*")
        return (await create_pat(actor.client, scopes))["token"]

    async def add_env(self, url: str = BASE_URL) -> None:
        result = await self.run("env", "add", ENV_NAME, "--url", url)
        assert result.exit_code == 0, result.output

    async def login(self, token: str, *extra: str) -> Result:
        return await self.run(
            "--env", ENV_NAME, *extra, "login", "--token-stdin", input=f"{token}\n"
        )


@dataclass
class Actor:
    client: httpx.AsyncClient
    user_id: str
    tenant_id: str
    email: str


@pytest.fixture
async def make_actor(app):
    """``await make_actor()``: a signed-in admin owning a new tenant (or ``tenant_id``)."""
    from tenants.core.constants import SESSION_ACTIVE_TENANT

    stack: list[Any] = []

    async def factory(tenant_id: str | None = None) -> Actor:
        email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        user_id = await make_admin(app, email)
        tenant_id = await join_tenant(app, user_id, email, tenant_id)
        data = {"user_id": user_id, SESSION_ACTIVE_TENANT: tenant_id, "sm_csrf_token": CSRF}
        manager = session_client(app, data)
        client = await manager.__aenter__()
        stack.append(manager)
        return Actor(client, user_id, tenant_id, email)

    yield factory
    for manager in reversed(stack):
        await manager.__aexit__(None, None, None)


@pytest.fixture
async def smdev(app, tmp_path, monkeypatch) -> AsyncIterator[Smdev]:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    for var in ("SMDEV_ENV", "SMDEV_TOKEN", "SMDEV_YES"):
        monkeypatch.delenv(var, raising=False)
    loop = asyncio.get_running_loop()
    yield Smdev(app, loop, LoopBridgeTransport(app, loop), FakeKeyring())


@pytest.fixture
def make_user(app):
    """``await make_user()``: a plain (non-admin) user; returns ``(user_id, email)``."""

    async def factory() -> tuple[str, str]:
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"
        return await create_user(app, email), email

    return factory
