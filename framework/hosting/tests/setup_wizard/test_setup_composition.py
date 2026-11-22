"""Schema-free coverage of validation order and pending-step composition."""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from simple_module_core.web.setup_steps import SetupAction, SetupField, SetupRegistry, SetupStep
from simple_module_hosting.pipeline.setup_gate import STEP_MIGRATIONS
from simple_module_hosting.setup_wizard.composition import migration_follow_up
from simple_module_hosting.setup_wizard.payloads import steps_payload
from simple_module_hosting.setup_wizard.routes import run_step_action
from starlette.requests import Request


def _scenario(
    *, invalid=False, fail=False, history=None, complete_after_migration=False, missing_table=False
):
    events = []
    state = {"migrated": False}

    async def migrated(app):
        return state["migrated"]

    async def done(app):
        if missing_table and not state["migrated"]:
            raise RuntimeError("no such table")
        return complete_after_migration and state["migrated"]

    async def migrate(request, data):
        events.append("migrate")
        state["migrated"] = True
        return {"migration": {"is_current": True}}

    async def validate(request, data):
        events.append("validate")
        if invalid:
            raise HTTPException(422, "Invalid password")

    async def create(request, data):
        events.append("create")
        if fail:
            raise RuntimeError("secret SQL connection detail")
        return {"created": True}

    registry = SetupRegistry()
    registry.add(
        SetupStep(
            STEP_MIGRATIONS,
            "Migrate",
            migrated,
            order=20,
            action=SetupAction(migrate),
        )
    )
    registry.add(
        SetupStep(
            "plugin.first",
            "First",
            done,
            order=30,
            action=SetupAction(
                create, fields=[SetupField("email", "Email")], validate_before_migrations=validate
            ),
        )
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(setup_registry=registry),
            migration={"is_current": False, "current_revision": history},
        )
    )

    async def receive():
        return {"type": "http.request", "body": json.dumps({"email": "a@b.co"}).encode()}

    request = Request({"type": "http", "app": app, "session": {}, "state": {}}, receive)
    return request, events, state


async def test_validate_migrate_then_follow_up():
    request, events, state = _scenario()
    await run_step_action(STEP_MIGRATIONS, request)
    assert events == ["validate", "migrate", "create"]
    assert state["migrated"]


async def test_invalid_data_never_calls_migration():
    request, events, state = _scenario(invalid=True)
    with pytest.raises(HTTPException) as exc:
        await run_step_action(STEP_MIGRATIONS, request)
    assert exc.value.status_code == 422
    assert events == ["validate"]
    assert not state["migrated"]


async def test_failed_follow_up_saves_safe_recovery_error():
    request, events, state = _scenario(fail=True)
    result = await run_step_action(STEP_MIGRATIONS, request)
    assert events == ["validate", "migrate", "create"]
    assert result["redirect"] == "/setup"
    assert state["migrated"]
    assert request.session["setup_error"] == {"step": "plugin.first"}


async def test_history_never_composes_steps():
    request, events, _state = _scenario(history="existing")
    await run_step_action(STEP_MIGRATIONS, request)
    assert events == ["migrate"]


async def test_completed_follow_up_is_not_invoked():
    request, events, _state = _scenario(complete_after_migration=True)
    await run_step_action(STEP_MIGRATIONS, request)
    assert events == ["validate", "migrate"]


async def test_missing_tables_still_offer_one_combined_form():
    request, _events, _state = _scenario(missing_table=True)
    registry = request.app.state.sm.setup_registry
    pending = {s.id for s in await registry.incomplete_all(request.app)}
    assert pending == {STEP_MIGRATIONS}
    follow_up = await migration_follow_up(request)
    follow_up.description = "An account to manage this install."
    payload = steps_payload(registry, pending, follow_up=follow_up)
    forms = [s for s in payload if s["action"]]
    assert [s["id"] for s in forms] == [STEP_MIGRATIONS]
    assert [f["name"] for f in forms[0]["action"]["fields"]] == ["email"]
    assert forms[0]["action"]["title"] == "First"
    assert forms[0]["action"]["description"] == (
        "An account to manage this install. The database will be set up first."
    )
    assert forms[0]["title"] == "Migrate"
    assert payload[1]["complete"] is False


async def test_no_local_account_step_keeps_migrate_only():
    request, events, state = _scenario()
    registry = SetupRegistry()
    registry.add(request.app.state.sm.setup_registry.get(STEP_MIGRATIONS))
    request.app.state.sm.setup_registry = registry
    await run_step_action(STEP_MIGRATIONS, request)
    assert events == ["migrate"]
    assert state["migrated"]


async def test_migration_error_does_not_run_follow_up():
    request, events, state = _scenario()

    async def fail_migration(request, data):
        raise HTTPException(500, "Migrations failed; see the server log.")

    request.app.state.sm.setup_registry.get(STEP_MIGRATIONS).action.handler = fail_migration
    with pytest.raises(HTTPException) as exc:
        await run_step_action(STEP_MIGRATIONS, request)
    assert exc.value.status_code == 500
    assert events == ["validate"]
    assert not state["migrated"]
    assert not request.session


async def test_error_after_follow_up_commit_does_not_redirect_to_closed_wizard():
    request, _events, state = _scenario()
    step = request.app.state.sm.setup_registry.get("plugin.first")

    async def completed(app):
        return state.get("created", False)

    async def commit_then_fail(request, data):
        state["created"] = True
        raise RuntimeError("refresh failed after commit")

    step.is_complete = completed
    step.action.handler = commit_then_fail
    result = await run_step_action(STEP_MIGRATIONS, request)
    assert "redirect" not in result
    assert not request.session
