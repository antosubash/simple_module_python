"""A Celery task's writes are audited like a request's (#498).

The worker never runs ``create_app``, so no ``DatabaseState`` carries the
audit sink there. ``sync_db`` binds the installed sink (the
``simple_module.audit_sinks`` entry point ``audit_log`` publishes) to its own
engine instead.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from background_tasks import sync_db
from celery import Celery
from simple_module_db import create_module_base
from simple_module_db.audit_sinks import discover_audit_callback
from sqlalchemy import create_engine, select
from sqlmodel import Field

audit_models = pytest.importorskip("audit_log.models")
AuditEntry = audit_models.AuditEntry

_Base = create_module_base("bgaudit")


class BgAuditWidget(_Base, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "bgaudit_widget"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=50)


@pytest.fixture
def worker_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    # The conftest strips the sink from worker engines; this suite wants it.
    monkeypatch.setattr(sync_db, "discover_audit_callback", discover_audit_callback)
    url = f"sqlite:///{tmp_path}/worker_audit.db"
    engine = create_engine(url)
    _Base.metadata.create_all(engine)
    AuditEntry.metadata.create_all(engine)
    engine.dispose()
    sync_db.set_database_url(url)
    yield url
    sync_db.dispose_sync_engine()


@pytest.fixture
def eager_celery() -> Celery:
    celery = Celery("bg_worker_audit")
    celery.conf.update(task_always_eager=True, task_eager_propagates=True)
    return celery


def _audit_rows() -> list[tuple[str, str, str]]:
    with sync_db.sync_session() as s:
        rows = s.execute(select(AuditEntry.entity_type, AuditEntry.entity_id, AuditEntry.action))
        return [tuple(r) for r in rows]


def test_the_audit_log_publishes_its_sink() -> None:
    from audit_log.capture import audit_callback

    assert discover_audit_callback() is audit_callback


def test_an_eager_task_write_produces_an_audit_row(worker_db, eager_celery) -> None:
    @eager_celery.task(name="bgaudit.create_widget")
    def create_widget(name: str) -> int | None:
        with sync_db.sync_session() as s:
            widget = BgAuditWidget(name=name)
            s.add(widget)
            s.flush()
            return widget.id

    widget_id = create_widget.delay("gear").get()

    assert _audit_rows() == [("BgAuditWidget", str(widget_id), "created")]


def test_updates_and_deletes_in_a_task_are_audited(worker_db, eager_celery) -> None:
    with sync_db.sync_session() as s:
        widget = BgAuditWidget(name="old")
        s.add(widget)
    widget_id = widget.id

    @eager_celery.task(name="bgaudit.rename_then_delete")
    def rename_then_delete(pk: int) -> None:
        with sync_db.sync_session() as s:
            row = s.get(BgAuditWidget, pk)
            row.name = "new"
        with sync_db.sync_session() as s:
            s.delete(s.get(BgAuditWidget, pk))

    rename_then_delete.delay(widget_id).get()

    rows = _audit_rows()
    assert {entity for entity, _, _ in rows} == {"BgAuditWidget"}
    assert sorted(action for _, _, action in rows) == ["created", "deleted", "updated"]


def test_without_a_sink_the_worker_writes_no_audit_rows(worker_db, monkeypatch) -> None:
    monkeypatch.setattr(sync_db, "discover_audit_callback", lambda: None)
    sync_db.dispose_sync_engine()
    sync_db.set_database_url(worker_db)

    with sync_db.sync_session() as s:
        s.add(BgAuditWidget(name="quiet"))

    assert _audit_rows() == []


def test_a_durable_handlers_write_on_the_outbox_engine_is_audited(worker_db) -> None:
    """The outbox worker builds its own async engine; it carries the sink too."""
    from background_tasks.outbox_loop import run_on_worker_loop, stop_worker_loop
    from background_tasks.outbox_worker import worker_session_factory

    factory = worker_session_factory()

    async def _handler_write() -> None:
        async with factory() as session:
            session.add(BgAuditWidget(name="durable"))
            await session.commit()

    try:
        run_on_worker_loop(_handler_write)
    finally:
        stop_worker_loop()

    assert [(e, a) for e, _, a in _audit_rows()] == [("BgAuditWidget", "created")]
