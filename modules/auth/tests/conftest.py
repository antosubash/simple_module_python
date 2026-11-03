"""Shared renewal harness for the #738 coordination tests."""

import asyncio
import copy
import time
from types import SimpleNamespace

import pytest
from auth.contracts.schemas import UserContext
from auth.oidc_common.renewal import refresh_session
from auth.oidc_common.session import SessionKeys
from simple_module_core.leases import configure_leases, reset_lease_backend
from simple_module_db.leases import DbLeaseBackend
from starlette.requests import Request


@pytest.fixture(params=["oidc", "keycloak"])
async def renewal(request, tmp_path):
    from importlib import import_module

    from auth.models import Base
    from simple_module_db.leases import LeaseRow
    from simple_module_db.session import init_db

    db_state = init_db(f"sqlite+aiosqlite:///{tmp_path}/refresh.db")
    async with db_state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(LeaseRow.metadata.create_all)

    tokens = import_module(f"{request.param}.tokens")
    keys = SessionKeys("user_ctx", f"{request.param}_refresh_token", "retry", "attempted")
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(
                db=db_state,
                settings=SimpleNamespace(secret_key="test-secret"),
            )
        )
    )
    configure_leases(DbLeaseBackend(db_state.engine))
    session = {
        "user_ctx": UserContext(
            id="user", email="old@example.com", name="Old", roles=["old"]
        ).to_session_dict(),
        keys.refresh: tokens.seal_refresh_token(app, "old"),
        "expires_at": int(time.time()) - 1,
        "oidc_session_id": "opaque-session",
        "gate": "preserved",
    }
    calls = []

    async def refresh(token):
        calls.append(token)
        # The grant stays in flight so a second request has to wait on the lease.
        await asyncio.sleep(refresh.delay)  # intentional-sleep: in-flight grant
        if refresh.error is not None:
            raise refresh.error
        return {"refresh_token": "rotated"}

    refresh.delay = 0.1
    refresh.error = None

    async def validate(_):
        return {"sub": "user", "exp": int(time.time()) + 300}

    async def matches(*_):
        return True

    def make_request(cookie=None):
        return Request(
            {
                "type": "http",
                "app": app,
                "session": copy.deepcopy(
                    session if cookie is None else cookie,
                ),
            }
        )

    async def renew(req):
        return await refresh_session(
            req,
            keys=keys,
            cache=object(),
            open_token=tokens.open_refresh_token,
            store_token=tokens.store_refresh_token,
            refresh=refresh,
            validate=validate,
            matches_identity=matches,
            to_context=lambda claims, cache_id: UserContext(
                id=cache_id, email="new@example.com", name="New", roles=["new"]
            ),
        )

    yield SimpleNamespace(**locals())
    reset_lease_backend()
    await db_state.engine.dispose()
