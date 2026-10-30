"""Generic store mutations cannot bypass module validation (#690)."""

import pytest
from simple_module_db.stored_settings import Setting


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("PUT", "/api/settings/system/users.allow_signup", {"value": "true"}),
        ("POST", "/api/settings/", {"key": "users.allow_signup", "value": "true"}),
    ],
)
async def test_generic_module_writes_are_refused(authenticated_client, app, method, path, body):
    original = app.state.users.settings.allow_signup
    response = await authenticated_client.request(method, path, json=body)
    assert response.status_code == 422, response.text
    assert "/admin/settings/" in response.text
    assert app.state.users.settings.allow_signup == original
    response = await authenticated_client.get("/api/settings/system/users.allow_signup")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [
        ("PUT", "/api/settings/{id}"),
        ("DELETE", "/api/settings/{id}"),
        ("DELETE", "/api/settings/system/users.allow_signup"),
    ],
)
async def test_existing_module_rows_cannot_be_mutated_generically(
    authenticated_client, app, method, path
):
    async with app.state.sm.db.session_factory() as db:
        row = Setting(key="users.allow_signup", value="false", value_type="bool")
        db.add(row)
        await db.commit()
        row_id = row.id
    response = await authenticated_client.request(
        method, path.format(id=row_id), json={"value": "true"} if method == "PUT" else None
    )
    assert response.status_code == 422, response.text
    assert "/admin/settings/" in response.text
    response = await authenticated_client.get("/api/settings/system/users.allow_signup")
    assert response.json()["value"] == "false"


def test_browse_does_not_suggest_module_keys():
    from types import SimpleNamespace

    from fastapi import FastAPI
    from settings.known_keys import build
    from simple_module_core.module_settings import register_module_settings
    from users.settings import UsersSettings

    app = FastAPI()
    app.state.sm = SimpleNamespace(modules=[])
    register_module_settings(app, "users", UsersSettings, lambda s: SimpleNamespace(settings=s))
    assert not any(entry["key"].startswith("users.") for entry in build(app))


async def test_tenant_row_for_module_key_stays_generically_writable(authenticated_client, app):
    """Only system rows are the module's own value; tenant overrides have no other route."""
    async with app.state.sm.db.session_factory() as db:
        row = Setting(
            key="users.allow_signup",
            value="false",
            value_type="bool",
            scope="tenant",
            scope_id="acme",
        )
        db.add(row)
        await db.commit()
        row_id = row.id
    response = await authenticated_client.put(f"/api/settings/{row_id}", json={"value": "true"})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/admin/settings/store", {"key": "users.allow_signup", "value": "true"}),
        ("PUT", "/admin/settings/{id}", {"value": "true"}),
        ("DELETE", "/admin/settings/{id}", None),
    ],
)
async def test_view_routes_flash_error_instead_of_raw_422(
    authenticated_client, app, method, path, body
):
    """Inertia form routes redirect back with errors; a raw JSON 422 breaks the page."""
    async with app.state.sm.db.session_factory() as db:
        row = Setting(key="users.allow_signup", value="false", value_type="bool")
        db.add(row)
        await db.commit()
        row_id = row.id
    response = await authenticated_client.request(method, path.format(id=row_id), json=body)
    assert response.status_code == 303, response.text
    response = await authenticated_client.get("/api/settings/system/users.allow_signup")
    assert response.json()["value"] == "false"


async def test_orphaned_module_row_stays_deletable(authenticated_client, app):
    """A row for a field the module no longer declares has no editor to clear it."""
    async with app.state.sm.db.session_factory() as db:
        db.add(Setting(key="users.no_such_field", value="x", value_type="str"))
        await db.commit()
    response = await authenticated_client.delete("/api/settings/system/users.no_such_field")
    assert response.status_code in (200, 204), response.text
