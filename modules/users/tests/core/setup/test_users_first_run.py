"""One submission on an empty schema; schema history always prevents composition."""

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from simple_module_hosting.boot.app_builder import create_app
from simple_module_hosting.boot.migrations import migration_status
from simple_module_hosting.pipeline.setup_gate import STEP_MIGRATIONS
from simple_module_hosting.setup_wizard.migrate import apply_migrations
from simple_module_test.web.setup_wizard import post_step, wizard_client, wizard_headers
from sqlalchemy import select
from users.core.setup import STEP_ADMINISTRATOR
from users.models import User

_INPUT = {"email": "first@example.com", "password": "SetupPass1!"}


@pytest.fixture
async def fresh_app(settings, tmp_path, monkeypatch, request):
    # No create_all or seeded account: exercise the missing-table predicates too.
    monkeypatch.setenv("SM_PROJECT_ROOT", str(Path.cwd()))
    provider = getattr(request, "param", "users")
    module = {"users": "Users", "keycloak": "Keycloak", "oidc": "Oidc"}[provider]
    app = create_app(
        settings.model_copy(
            update={
                "database_url": f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}",
                "modules_enabled": ["Auth", module],
                "auth_provider": provider,
                "multi_tenant": False,
            }
        )
    )
    app.state.migration = await migration_status(app.state.sm.db.engine)
    try:
        yield app
    finally:
        await app.state.sm.db.engine.dispose()


async def _admins(app):
    async with app.state.sm.db.session_factory() as session:
        return list(await session.scalars(select(User.email).where(User.is_superuser.is_(True))))


async def test_fresh_form_and_one_post_complete_setup(fresh_app):
    async with wizard_client(fresh_app) as client:
        page = await client.get("/setup", headers={"X-Inertia": "true"})
        forms = [s for s in page.json()["props"]["steps"] if s["action"]]
        assert len(forms) == 1
        assert forms[0]["id"] == STEP_MIGRATIONS
        assert [f["name"] for f in forms[0]["action"]["fields"]] == [
            "email",
            "password",
            "full_name",
        ]
        response = await post_step(client, STEP_MIGRATIONS, _INPUT)
        assert response.status_code == 200, response.text
        assert (await client.get("/setup")).status_code == 404
        assert (await client.get("/", follow_redirects=False)).headers.get("location") != "/setup"
    assert (await migration_status(fresh_app.state.sm.db.engine))["is_current"]
    assert await _admins(fresh_app) == ["first@example.com"]


@pytest.mark.parametrize(
    "data",
    [_INPUT | {"password": p} for p in ("short", "12345678", "        ")]
    + [_INPUT | {"email": "not-email"}, {}],
)
async def test_invalid_input_leaves_schema_untouched(fresh_app, data):
    async with wizard_client(fresh_app) as client:
        response = await post_step(client, STEP_MIGRATIONS, data)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]
    with closing(sqlite3.connect(fresh_app.state.sm.db.engine.url.database)) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


async def test_creation_failure_recovers_to_admin_form(fresh_app, monkeypatch):
    from users.core import setup_action

    real_create = setup_action.create_admin

    async def fail(*args, **kwargs):
        raise RuntimeError("private database connection detail")

    monkeypatch.setattr(setup_action, "create_admin", fail)
    async with wizard_client(fresh_app) as client:
        response = await post_step(client, STEP_MIGRATIONS, _INPUT)
        assert response.status_code == 200, response.text
        assert response.json()["redirect"] == "/setup"
        page = await client.get("/setup", headers={"X-Inertia": "true"})
        props = page.json()["props"]
        forms = [s for s in props["steps"] if s["action"]]
        assert [s["id"] for s in forms] == [STEP_ADMINISTRATOR]
        assert props["setupError"]["step"] == STEP_ADMINISTRATOR
        assert "private database" not in props["setupError"]["message"]
        assert "migration" in props["setupError"]["message"].lower()
        monkeypatch.setattr(setup_action, "create_admin", real_create)
        retry = await post_step(client, STEP_ADMINISTRATOR, _INPUT)
        assert retry.status_code == 200, retry.text
        assert (await client.get("/setup")).status_code == 404
    assert await _admins(fresh_app) == ["first@example.com"]


async def test_existing_history_keeps_separate_steps(fresh_app, monkeypatch):
    await apply_migrations(SimpleNamespace(app=fresh_app, state=SimpleNamespace()), {})
    behind = {
        "current_revision": "old",
        "head_revision": "new",
        "is_current": False,
        "pending_count": 1,
    }

    async def still_behind(*args, **kwargs):
        return dict(behind)

    monkeypatch.setattr("simple_module_hosting.boot.migrations.migration_status", still_behind)
    fresh_app.state.migration = dict(behind)
    async with wizard_client(fresh_app) as client:
        page = await client.get("/setup", headers={"X-Inertia": "true"})
        forms = {s["id"]: s["action"] for s in page.json()["props"]["steps"] if s["action"]}
        assert forms[STEP_MIGRATIONS]["fields"] == []
        assert forms[STEP_ADMINISTRATOR]["fields"]
        response = await post_step(client, STEP_MIGRATIONS, _INPUT)
        assert response.status_code == 409
    assert await _admins(fresh_app) == []


async def test_concurrent_combined_submissions_create_one_admin(fresh_app):
    clients = [wizard_client(fresh_app) for _ in range(2)]
    try:
        headers = [await wizard_headers(client) for client in clients]
        responses = await asyncio.gather(
            *(
                client.post(
                    f"/setup/steps/{STEP_MIGRATIONS}",
                    json=_INPUT | {"email": f"first{n}@example.com"},
                    headers=header,
                )
                for n, (client, header) in enumerate(zip(clients, headers, strict=True))
            )
        )
        assert sum(r.status_code == 200 for r in responses) == 1
        assert all(r.status_code in (200, 404, 409) for r in responses)
        assert len(await _admins(fresh_app)) == 1
    finally:
        for client in clients:
            await client.aclose()


@pytest.mark.parametrize("fresh_app", ["keycloak", "oidc"], indirect=True)
async def test_external_provider_keeps_migrate_only(fresh_app):
    assert [s.id for s in fresh_app.state.sm.setup_registry.required_steps] == [STEP_MIGRATIONS]
    async with wizard_client(fresh_app) as client:
        page = await client.get("/setup", headers={"X-Inertia": "true"})
        forms = [s for s in page.json()["props"]["steps"] if s["action"]]
        assert len(forms) == 1
        assert forms[0]["action"]["fields"] == []
        response = await post_step(client, STEP_MIGRATIONS)
        assert response.status_code == 200, response.text
        assert (await client.get("/setup")).status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        _INPUT | {"password": "short"},
        _INPUT | {"password": "12345678"},
        _INPUT | {"password": "        "},
        _INPUT | {"email": "not-email"},
        {},
    ],
)
async def test_schema_free_validation_reuses_user_policy(data):
    from fastapi import HTTPException
    from users.core.setup_action import validate_administrator_input

    # No app/engine: a validator that attempted DB access would fail this test.
    with pytest.raises(HTTPException) as exc:
        await validate_administrator_input(SimpleNamespace(), data)
    assert exc.value.status_code == 422
