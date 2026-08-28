"""The setup wizard's admin route must enforce the real password policy.

Found in browser QA: ``"        "`` is eight characters, so a raw ``min_length=8``
accepted it — and ``/setup/administrator`` is unauthenticated, so an anonymous
caller could create the install's first superuser with a whitespace-only
password. The route reimplemented a subset of ``UserManager.validate_password``
rather than calling it, which is how the two drifted apart; it delegates now.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.anyio


def _mount(app):
    from host.routes_setup import router as setup_router

    app.include_router(setup_router)
    return app


async def _post(app, password: str, email: str = "root@example.com") -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_mount(app)), base_url="http://testserver"
    ) as client:
        # Accept: application/json is what the wizard's fetch sends. Without
        # it the host renders an Inertia error *page* for a 4xx and the
        # reason never reaches the operator.
        return await client.post(
            "/setup/administrator",
            json={"email": email, "password": password},
            headers={"Accept": "application/json"},
        )


@pytest.mark.parametrize(
    "password,why",
    [
        ("        ", "whitespace-only, exactly eight characters"),
        ("   a    ", "one real character padded to eight"),
        ("short", "under the minimum"),
        ("", "empty"),
        ("12345678", "all digits — the policy rejects these"),
    ],
)
async def test_weak_passwords_are_refused(setup_pending_app, password: str, why: str) -> None:
    resp = await _post(setup_pending_app, password)

    assert resp.status_code == 422, f"accepted a password that is {why}: {resp.text[:120]}"


async def test_the_refusal_says_why(setup_pending_app) -> None:
    """The operator has to be able to act on it — this route's 422 is rendered
    straight into the wizard's error line."""
    resp = await _post(setup_pending_app, "        ")

    detail = resp.json().get("detail")
    assert isinstance(detail, str) and detail, f"unusable error body: {resp.text[:200]}"
    assert "8" in detail or "characters" in detail.lower()


async def test_a_strong_password_is_accepted(setup_pending_app) -> None:
    resp = await _post(setup_pending_app, "QaSetupPass1!")

    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] is True
