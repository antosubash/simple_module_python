"""Negative-authorization sweep across every endpoint behind RequiresPermission.

Every endpoint guarded by ``RequiresPermission(...)`` must answer 403 when the
caller is authenticated but not an admin. The decorator presence alone isn't
enough — even one missing ``Depends(...)`` would leak admin-only data to
ordinary users.

The matrix below is exhaustive across the modules that ship with the framework
(users, permissions, settings, feature_flags, background_tasks, file_storage).
A new protected endpoint should be added here at the same time as it gains its
``RequiresPermission`` dependency.
"""

from __future__ import annotations

import uuid

import pytest

_FAKE_ID = uuid.uuid4()
_PROTECTED_ENDPOINTS: tuple[tuple[str, str, dict | None], ...] = (
    # users — admin sub-router
    ("GET", "/api/users/admin", None),
    ("POST", "/api/users/admin/invite", {"email": "x@y.test", "role_names": []}),
    ("PATCH", f"/api/users/admin/{_FAKE_ID}/disable", None),
    ("PATCH", f"/api/users/admin/{_FAKE_ID}/enable", None),
    ("PUT", f"/api/users/admin/{_FAKE_ID}/roles", {"role_names": []}),
    ("PATCH", f"/api/users/admin/{_FAKE_ID}/verify", None),
    ("POST", f"/api/users/admin/{_FAKE_ID}/reset-password-link", None),
    (
        "POST",
        "/api/users/admin",
        {"email": "x@y.test", "password": "SecurePass1!", "role_names": []},
    ),
    ("PATCH", f"/api/users/admin/{_FAKE_ID}", {"email": "x@y.test"}),
    ("DELETE", f"/api/users/admin/{_FAKE_ID}", None),
    # permissions — root GET lists registered groups (PERM_VIEW)
    ("GET", "/api/permissions/", None),
    ("GET", f"/api/permissions/roles/{_FAKE_ID}", None),
    ("PUT", f"/api/permissions/roles/{_FAKE_ID}", {"permissions": []}),
    ("GET", f"/api/permissions/users/{_FAKE_ID}", None),
    ("PUT", f"/api/permissions/users/{_FAKE_ID}", {"permissions": []}),
    # settings — both the scoped CRUD and the module-config endpoints
    ("GET", "/api/settings/", None),
    ("POST", "/api/settings/", {"key": "x", "value": "1", "value_type": "string"}),
    ("PUT", "/api/settings/system/anykey", {"value": "1", "value_type": "string"}),
    ("DELETE", "/api/settings/system/anykey", None),
    ("GET", "/api/settings/modules", None),
    ("PUT", "/api/settings/modules/users", {}),
    ("DELETE", "/api/settings/modules/users/allow_signup", None),
    # feature flags
    ("GET", "/api/feature_flags/", None),
    ("PUT", "/api/feature_flags/anyflag", {"enabled": True}),
    ("DELETE", "/api/feature_flags/anyflag", None),
    # background tasks (admin router under /admin)
    ("GET", "/api/background_tasks/admin/executions", None),
    ("GET", "/api/background_tasks/admin/workers", None),
    ("POST", f"/api/background_tasks/admin/executions/{_FAKE_ID}/retry", None),
    # file_storage's list/upload/download/delete are deliberately granted to
    # the standard `user` role, so they're NOT in the negative-authz matrix.
)


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "path", "json_body"), _PROTECTED_ENDPOINTS)
async def test_protected_endpoint_rejects_non_admin(
    user_client, method: str, path: str, json_body: dict | None
) -> None:
    """A logged-in non-admin user must be answered 403 by every protected route.

    A regression here means the ``Depends(RequiresPermission(...))`` was dropped
    or a non-admin role gained a wildcard mapping it shouldn't have.
    """
    resp = await user_client.request(method, path, json=json_body, follow_redirects=False)
    assert resp.status_code == 403, (
        f"{method} {path} returned {resp.status_code}, "
        f"expected 403 for non-admin caller (body: {resp.text!r})"
    )


@pytest.mark.anyio
async def test_admin_endpoints_still_pass_for_admin(admin_client) -> None:
    """Sanity check: the same routes work for an admin caller.

    Without this anchor a global regression that returned 403 for everyone
    would still satisfy the parametrized 403 assertion above.
    """
    resp = await admin_client.get("/api/users/admin")
    assert resp.status_code == 200
    resp = await admin_client.get("/api/feature_flags/")
    assert resp.status_code == 200
