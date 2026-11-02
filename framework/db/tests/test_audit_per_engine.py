"""The audit sink is bound per engine, never process-wide (#498).

``create_app`` builds one ``DatabaseState`` per app; ``register_listeners``
binds it to that app's engine. Two apps in one process (tests, a CLI next to
an app) must each audit through their own sink, and a bare sync engine (the
Celery worker's) is audited only when its ``EngineTenancy`` names a sink.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from _audit_models import AuditBase, AuditTestItem
from simple_module_core.correlation import correlation_id
from simple_module_db.audit import AuditRecord
from simple_module_db.listeners import attach_session_listeners, register_listeners
from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
from simple_module_db.session import DatabaseState, init_db
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class _Recorder:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def __call__(self, session: Session, records: list[AuditRecord]) -> None:
        self.records.extend(records)


async def _state(callback: _Recorder | None) -> DatabaseState:
    state = init_db("sqlite+aiosqlite:///:memory:")
    state.audit_callback = callback
    register_listeners(state)
    async with state.engine.begin() as conn:
        await conn.run_sync(AuditBase.metadata.create_all)
    return state


async def _write(state: DatabaseState, name: str) -> None:
    async with state.session_factory() as session:
        session.add(AuditTestItem(name=name))
        await session.commit()


@pytest.fixture
async def two_apps() -> AsyncGenerator[tuple[DatabaseState, DatabaseState, _Recorder]]:
    """App A audits; app B (built second, so the old global's winner) does not."""
    recorder = _Recorder()
    a = await _state(recorder)
    b = await _state(None)
    try:
        yield a, b, recorder
    finally:
        await a.engine.dispose()
        await b.engine.dispose()


async def test_a_later_app_without_auditing_does_not_switch_off_the_first(two_apps):
    a, _b, recorder = two_apps
    await _write(a, "from-a")
    assert [(r.entity_type, r.action) for r in recorder.records] == [("AuditTestItem", "created")]


async def test_the_unaudited_app_does_not_reach_the_other_apps_sink(two_apps):
    _a, b, recorder = two_apps
    await _write(b, "from-b")
    assert recorder.records == []


async def test_shutting_down_one_apps_audit_leaves_the_other_alone(two_apps):
    a, b, recorder = two_apps
    b.audit_callback = None  # what audit_log's on_shutdown does to its app
    await _write(a, "still-audited")
    assert len(recorder.records) == 1


async def test_two_audited_apps_keep_their_own_sinks():
    first, second = _Recorder(), _Recorder()
    a, b = await _state(first), await _state(second)
    try:
        await _write(a, "a1")
        await _write(b, "b1")
        await _write(b, "b2")
    finally:
        await a.engine.dispose()
        await b.engine.dispose()
    assert (len(first.records), len(second.records)) == (1, 2)


class _BareSession(Session):
    """A worker-style session class with no ``DatabaseState`` behind it."""


def _bare_factory(callback: _Recorder | None) -> sessionmaker[Session]:
    engine = create_engine("sqlite://")
    AuditBase.metadata.create_all(engine)
    attach_session_listeners(_BareSession)
    bind_engine_policy(engine, EngineTenancy(tenant_strict=False, audit_callback=callback))
    return sessionmaker(bind=engine, class_=_BareSession)


def test_a_bare_engine_is_audited_through_its_engine_tenancy():
    recorder = _Recorder()
    factory = _bare_factory(recorder)
    token = correlation_id.set("job-42")
    try:
        with factory() as session:
            session.add(AuditTestItem(name="worker"))
            session.commit()
    finally:
        correlation_id.reset(token)
    [record] = recorder.records
    assert (record.entity_type, record.action, record.correlation_id) == (
        "AuditTestItem",
        "created",
        "job-42",
    )


def test_a_bare_engine_without_a_sink_is_not_audited():
    recorder = _Recorder()
    _bare_factory(recorder)  # a sibling engine that *is* audited
    with _bare_factory(None)() as session:
        session.add(AuditTestItem(name="quiet"))
        session.commit()
    assert recorder.records == []


def test_hosting_reexports_the_core_correlation_id():
    from simple_module_hosting.logging import correlation_id as hosting_cid

    assert hosting_cid is correlation_id
