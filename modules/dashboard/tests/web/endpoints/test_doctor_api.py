"""Doctor results and re-run over the API with tokens (#1178)."""

from __future__ import annotations

from _api_tokens_support import CSRF, admin_session, bearer_client, pat_for  # ty: ignore[import-not-found]
from dashboard.core.constants import Permissions
from simple_module_test.web.tenant_client import session_client

_DOCTOR = "/api/dashboard/doctor"
_INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


def test_permission_registered_and_not_mapped_to_tenant_roles(app):
    from simple_module_core.access.tenancy import TenantRole, tenant_role

    registry = app.state.sm.permissions
    assert registry.has(Permissions.DOCTOR)
    for role in TenantRole:
        assert Permissions.DOCTOR not in registry.role_map[tenant_role(role)]


async def test_doctor_pat_reads_same_keys_as_the_view_and_reruns(app):
    data = await admin_session(app)
    token = await pat_for(app, data, [Permissions.DOCTOR])
    async with bearer_client(app, token) as bc:
        resp = await bc.get(_DOCTOR)
        assert resp.status_code == 200, resp.text
        rerun = await bc.post(f"{_DOCTOR}/rerun")
        assert rerun.status_code == 200, rerun.text
    async with session_client(app, data) as client:
        page = await client.get("/admin/doctor/", headers=_INERTIA)
    assert page.status_code == 200, page.text
    # The page also carries the layout's shared props; the doctor data is a subset.
    assert set(resp.json()) <= set(page.json()["props"])
    for key, value in resp.json().items():
        assert page.json()["props"][key] == value or key in {"generated_at"}
    assert set(rerun.json()) == set(resp.json())


async def test_pat_without_doctor_scope_is_refused(app):
    data = await admin_session(app)
    token = await pat_for(app, data, [Permissions.VIEW])
    async with bearer_client(app, token) as bc:
        assert (await bc.get(_DOCTOR)).status_code == 403
        assert (await bc.post(f"{_DOCTOR}/rerun")).status_code == 403


async def test_rerun_invokes_the_runner_and_returns_its_finding(app):
    from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel

    finding = Diagnostic(
        level=DiagnosticLevel.WARNING,
        code="SM018",
        message="fixture finding",
        module_name="Fixture",
    )
    calls: list[int] = []

    def runner() -> list[Diagnostic]:
        calls.append(1)
        return [finding]

    app.state.sm.diagnostics.runner = runner
    data = await admin_session(app)
    token = await pat_for(app, data, [Permissions.DOCTOR])
    async with bearer_client(app, token) as bc:
        resp = await bc.post(f"{_DOCTOR}/rerun")
    assert resp.status_code == 200, resp.text
    assert calls == [1]
    inertia = next(c for c in resp.json()["checks"] if c["id"] == "inertia")
    assert inertia["status"] == "warn"
    assert [f["message"] for f in inertia["findings"]] == ["fixture finding"]


async def test_cookie_session_rerun_needs_csrf_token(app):
    data = await admin_session(app)
    async with session_client(app, data) as client:
        refused = await client.post(f"{_DOCTOR}/rerun")
        assert refused.status_code == 403
        assert "X-CSRF-Token" in refused.json()["detail"]
        ok = await client.post(f"{_DOCTOR}/rerun", headers={"X-CSRF-Token": CSRF})
        assert ok.status_code == 200, ok.text
