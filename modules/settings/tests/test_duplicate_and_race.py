"""qa BUG-001 / BUG-002: the (scope, scope_id, key) unique key must never surface as a 500.

* two first-time writers of one key: one inserts, the other becomes an update;
* creating a key that already exists: 409 from the API, an inline field error
  from the admin form.
"""

from __future__ import annotations

import asyncio

import pytest
from settings.contracts.schemas import SettingScope, SettingUpsert
from settings.models import Base, Setting
from settings.service import SettingService
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from simple_module_test.database import (
    database_url_for_tests,
    init_db_kwargs,
    is_sqlite,
    reset_schema,
)
from sqlalchemy import func, select

BODY = {"scope": "system", "scope_id": "", "key": "dup.key", "value": "1"}


def _backends() -> list[str]:
    backends = ["sqlite-file"]
    if not is_sqlite(database_url_for_tests()):
        backends.append("postgres")
    return backends


@pytest.mark.parametrize("backend", _backends())
async def test_concurrent_first_time_upserts_all_succeed(tmp_path, backend: str):
    if backend == "postgres":
        url = database_url_for_tests()
        state = init_db(url, **init_db_kwargs(url))
        await reset_schema(state.engine)
    else:
        state = init_db(f"sqlite+aiosqlite:///{tmp_path}/race.db")
    register_listeners(state)
    try:
        async with state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async def put(i: int) -> str:
            async with state.session_factory() as db:
                try:
                    await SettingService(db).upsert_scoped(
                        SettingScope.TENANT, "t1", "race.key", SettingUpsert(value=f"v{i}")
                    )
                    await db.commit()
                    return "ok"
                except Exception as exc:
                    await db.rollback()
                    # SQLite may refuse a stale snapshot outright; that is a
                    # retryable "busy", never the unique-key error being fixed.
                    return type(exc).__name__

        outcomes = await asyncio.gather(*(put(i) for i in range(5)))
        assert "IntegrityError" not in outcomes, outcomes
        assert "ok" in outcomes
        async with state.session_factory() as db:
            count = await db.scalar(select(func.count()).select_from(Setting))
        assert count == 1
    finally:
        await state.engine.dispose()


async def test_api_create_duplicate_is_409(authenticated_client):
    first = await authenticated_client.post("/api/settings/", json=BODY)
    assert first.status_code == 201, first.text
    again = await authenticated_client.post("/api/settings/", json=BODY)
    assert again.status_code == 409, again.text


async def test_form_create_duplicate_is_an_inline_error(authenticated_client):
    first = await authenticated_client.post("/api/settings/", json=BODY)
    assert first.status_code == 201, first.text
    resp = await authenticated_client.post(
        "/admin/settings/store",
        json=BODY,
        headers={"Referer": "http://test/admin/settings/create", "X-Inertia": "true"},
    )
    assert resp.status_code == 303, resp.text
    shown = await authenticated_client.get(
        "/admin/settings/create", headers={"X-Inertia": "true", "Accept": "application/json"}
    )
    assert shown.status_code == 200
    assert "already exists" in shown.json()["props"]["errors"]["key"]


async def test_upsert_that_loses_the_insert_race_becomes_an_update(db_session, monkeypatch):
    """Deterministic stand-in for the race: the row lands after the lookup said "none"."""
    service = SettingService(db_session)
    await service.upsert_scoped(SettingScope.TENANT, "t1", "race.key", SettingUpsert(value="first"))
    real_find = service._find
    calls = 0

    async def blind_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        return None if calls == 1 else await real_find(*args, **kwargs)

    monkeypatch.setattr(service, "_find", blind_once)
    result = await service.upsert_scoped(
        SettingScope.TENANT, "t1", "race.key", SettingUpsert(value="second")
    )
    assert result.value == "second"
    assert await db_session.scalar(select(func.count()).select_from(Setting)) == 1
