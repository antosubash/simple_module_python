"""Installation identity is internal metadata, never generic configuration (#986)."""

import pytest
from settings.contracts.schemas import SettingScope
from settings.core.service import SettingService
from simple_module_db.stored_settings import Setting
from simple_module_test import inertia_page
from sqlalchemy import select

KEY = "host.installation_id"
IDENTITY = "private-installation-identity"


@pytest.fixture
async def identity_row(app):
    async with app.state.sm.db.session_factory() as db:
        row = (await db.execute(select(Setting).where(Setting.key == KEY))).scalar_one_or_none()
        if row is None:
            row = Setting(key=KEY, value=IDENTITY)
            db.add(row)
        else:
            row.value = IDENTITY
        await db.commit()
        return row.id


@pytest.mark.parametrize(
    "path",
    [
        "/api/settings/",
        "/api/settings/?scope=system",
        "/api/settings/{id}",
        "/api/settings/system/host.installation_id",
        "/api/settings/resolve/host.installation_id",
        "/admin/settings/store",
        "/admin/settings/store?q=installation_id",
        "/admin/settings/{id}/edit",
        "/admin/settings/",
    ],
)
async def test_generic_reads_hide_identity(authenticated_client, identity_row, path):
    response = await authenticated_client.get(path.format(id=identity_row))
    assert response.status_code in (200, 404), response.text
    assert IDENTITY not in response.text
    assert KEY not in response.text
    if path == "/admin/settings/store?q=installation_id":
        props = inertia_page(response).props
        assert props["pagination"]["total"] == 0
        assert props["counts"]["all"] == 0


@pytest.mark.parametrize(
    "method,path,body,status",
    [
        ("POST", "/api/settings/", {"key": KEY, "value": "replaced"}, 422),
        ("PUT", "/api/settings/{id}", {"value": "replaced"}, 422),
        ("PUT", "/api/settings/system/host.installation_id", {"value": "replaced"}, 422),
        ("DELETE", "/api/settings/{id}", None, 422),
        ("DELETE", "/api/settings/system/host.installation_id", None, 422),
        ("POST", "/admin/settings/store", {"key": KEY, "value": "replaced"}, 303),
        ("PUT", "/admin/settings/{id}", {"value": "replaced"}, 303),
        ("DELETE", "/admin/settings/{id}", None, 303),
        (
            "PUT",
            "/api/settings/user/any-user/host.installation_id",
            {"value": "replaced"},
            422,
        ),
    ],
)
async def test_generic_mutations_cannot_change_identity(
    authenticated_client, app, identity_row, method, path, body, status
):
    response = await authenticated_client.request(method, path.format(id=identity_row), json=body)
    assert response.status_code == status, response.text
    async with app.state.sm.db.session_factory() as db:
        rows = (await db.execute(select(Setting).where(Setting.key == KEY))).scalars().all()
        assert [(row.id, row.value) for row in rows] == [(identity_row, IDENTITY)]


async def test_bulk_and_unmasked_reads_omit_internal_metadata(db_session):
    db_session.add(Setting(key=KEY, value=IDENTITY))
    db_session.add(Setting(key="ordinary", value="visible"))
    await db_session.flush()
    service = SettingService(db_session)
    for rows in (
        await service.list_all(),
        await service.list_by_scope(SettingScope.SYSTEM),
        await service.list_by_scope_unmasked(SettingScope.SYSTEM),
    ):
        assert [(row.key, row.value) for row in rows] == [("ordinary", "visible")]
    assert await service.get_resolved_value(KEY) is None
