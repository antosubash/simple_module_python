"""Session signing follows the live root, even within the request adopting it."""

import httpx
import pytest
from fastapi import Request
from itsdangerous import TimestampSigner
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings


def _app(root):
    app = create_app(
        Settings(
            _env_file=None,
            environment="testing",
            secret_key=root,
            modules_enabled=["Auth", "Users"],
        )
    )

    @app.post("/setup/test-adopt")
    async def adopt(request: Request):
        app.state.sm.settings.secret_key = "stored-root"
        request.session["marker"] = "after-setup"
        return {"ok": True}

    @app.get("/setup/test-session")
    async def session(request: Request):
        return {"marker": request.session.get("marker")}

    return app


async def test_session_cookie_uses_root_adopted_during_request():
    apps = [_app("first-ephemeral-root"), _app("peer-ephemeral-root")]
    try:
        cookies = []
        for app in apps:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/setup/test-adopt")
            assert response.status_code == 200
            cookie = response.cookies["session"]
            assert TimestampSigner("stored-root").unsign(cookie)
            cookies.append(cookie)
        for cookie in cookies:
            for app in apps:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get(
                        "/setup/test-session", headers={"Cookie": f"session={cookie}"}
                    )
                assert response.json() == {"marker": "after-setup"}
    finally:
        for app in apps:
            await app.state.sm.db.engine.dispose()


@pytest.mark.parametrize("root", ["", " \t\n"])
def test_session_signing_refuses_blank_roots(root):
    from simple_module_hosting.session import SessionMiddleware

    with pytest.raises(ValueError, match=r"root secret.*blank"):
        SessionMiddleware(lambda scope, receive, send: None, secret_key=root)


@pytest.mark.parametrize("root", ["", " \t\n"])
def test_dynamic_session_signing_refuses_blank_roots(root):
    from simple_module_hosting.session import SessionMiddleware

    middleware = SessionMiddleware(
        lambda scope, receive, send: None,
        secret_key="initial-root",
        secret_key_provider=lambda: root,
    )
    with pytest.raises(ValueError, match=r"root secret.*blank"):
        middleware.signer.sign(b"payload")
