"""The /setup wizard's HTTP surface, as ``create_app`` mounts it for every host.

``test_setup_closes_after_completion`` is the security-relevant one. Every
route here is unauthenticated by necessity — the wizard exists precisely when
no account exists — and one step action can run Alembic. What bounds that is
the routes refusing once setup is complete, so it is asserted rather than
assumed. The administrator action's own guarantees are pinned by the users
module's ``test_users_setup_wizard``.
"""

from __future__ import annotations

import logging

import pytest
from simple_module_core.setup_steps import SetupAction, SetupRegistry, SetupStep
from simple_module_hosting.setup_gate import STEP_MIGRATIONS
from simple_module_hosting.setup_wizard import report_unactionable_steps
from simple_module_test.setup_wizard import post_step, wizard_client, wizard_headers

pytestmark = pytest.mark.anyio

_STEP_ADMINISTRATOR = "users.administrator"


async def test_create_app_mounts_the_wizard(setup_pending_app) -> None:
    """No host-side router: a host that only calls create_app gets /setup."""
    async with wizard_client(setup_pending_app) as client:
        root = await client.get("/", follow_redirects=False)
        page = await client.get("/setup", follow_redirects=False)

    assert root.status_code == 302
    assert root.headers["location"] == "/setup"
    assert page.status_code == 200
    assert 'data-page="app"' in page.text
    assert "Setup/Wizard" in page.text


async def test_wizard_lists_steps_with_forms_for_pending_ones(setup_pending_app) -> None:
    async with wizard_client(setup_pending_app) as client:
        resp = await client.get("/setup", headers={"X-Inertia": "true"})

    props = resp.json()["props"]
    assert props["csrfToken"]
    steps = {s["id"]: s for s in props["steps"]}

    admin = steps[_STEP_ADMINISTRATOR]
    assert admin["complete"] is False
    assert [f["name"] for f in admin["action"]["fields"]] == ["email", "password", "full_name"]
    assert admin["action"]["submitLabel"] == "Create administrator"

    # The schema is at head, so its step is done and offers no form.
    assert steps[STEP_MIGRATIONS]["complete"] is True
    assert steps[STEP_MIGRATIONS]["action"] is None


async def test_connection_checks_are_reported(setup_pending_app) -> None:
    """The wizard reports each dependency by name with a reason attached."""
    async with wizard_client(setup_pending_app) as client:
        headers = await wizard_headers(client)
        resp = await client.post("/setup/test-connections", headers=headers)

    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()["checks"]}
    assert names == {"host.database", "background_tasks.redis"}


async def test_mutations_require_the_csrf_token(setup_pending_app) -> None:
    async with wizard_client(setup_pending_app) as client:
        await client.get("/setup")  # a session exists, but no token is echoed
        probe = await client.post("/setup/test-connections")
        action = await client.post(
            f"/setup/steps/{_STEP_ADMINISTRATOR}",
            json={"email": "root@example.com", "password": "SetupPass1!"},
        )

    assert probe.status_code == 403
    assert action.status_code == 403


async def test_setup_closes_after_completion(app) -> None:
    """Once setup is complete every /setup route answers 404.

    This is what bounds the migrations action — an unauthenticated endpoint
    that can execute Alembic. It must be unreachable on a configured install,
    and with 404 rather than a CSRF 403 that advertises it.
    """
    async with wizard_client(app) as client:
        for method, path in (
            ("GET", "/setup"),
            ("POST", "/setup/test-connections"),
            ("POST", f"/setup/steps/{STEP_MIGRATIONS}"),
            ("POST", f"/setup/steps/{_STEP_ADMINISTRATOR}"),
        ):
            resp = await client.request(method, path, json={})
            assert resp.status_code == 404, f"{method} {path} answered {resp.status_code}"


async def test_unknown_step_is_404(setup_pending_app) -> None:
    async with wizard_client(setup_pending_app) as client:
        resp = await post_step(client, "nobody.registered.this")

    assert resp.status_code == 404


async def test_a_completed_step_refuses_its_action(setup_pending_app) -> None:
    """Setup mode is on (no admin), but the schema step is done: 409, never a
    second Alembic run triggered anonymously."""
    async with wizard_client(setup_pending_app) as client:
        resp = await post_step(client, STEP_MIGRATIONS)

    assert resp.status_code == 409


async def test_boot_reports_required_steps_without_an_action(caplog) -> None:
    async def never(_app) -> bool:
        return False

    async def handler(_request, _data):
        return None

    registry = SetupRegistry()
    registry.add(
        SetupStep(id="a.actionable", title="a", is_complete=never, action=SetupAction(handler))
    )
    registry.add(SetupStep(id="b.out_of_band", title="b", is_complete=never))
    registry.add(SetupStep(id="c.optional", title="c", is_complete=never, required=False))

    with caplog.at_level(logging.WARNING, logger="simple_module_hosting.setup_wizard"):
        report_unactionable_steps(registry)

    reported = " ".join(r.getMessage() for r in caplog.records)
    assert "b.out_of_band" in reported
    assert "a.actionable" not in reported
    assert "c.optional" not in reported
