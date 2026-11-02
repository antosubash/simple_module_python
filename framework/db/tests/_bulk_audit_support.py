"""Shared fixture for the bulk-audit tests (#557): an audited engine with a recorder sink."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from _audit_models import AuditBase, AuditTestItem
from _models import _TenantBase
from simple_module_db.audit import AuditRecord
from simple_module_db.listeners import register_listeners
from simple_module_db.session import DatabaseState, init_db
from simple_module_test.database import database_url_for_tests, init_db_kwargs, reset_schema
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

_URL = database_url_for_tests()


class _Recorder:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def __call__(self, session: Session, records: list[AuditRecord]) -> None:
        self.records.extend(records)

    def summary(self) -> list[tuple[str, str, str]]:
        return [(r.entity_type, r.action, r.entity_id) for r in self.records]


async def audited_engine() -> AsyncGenerator[tuple[DatabaseState, AsyncSession, _Recorder]]:
    recorder = _Recorder()
    state = init_db(_URL, **init_db_kwargs(_URL))
    state.audit_callback = recorder
    register_listeners(state)
    await reset_schema(state.engine)
    async with state.engine.begin() as conn:
        await conn.run_sync(AuditBase.metadata.create_all)
        await conn.run_sync(_TenantBase.metadata.create_all)
    async with state.session_factory() as session:
        session.add_all([AuditTestItem(name=f"n{i}", value=i) for i in range(3)])
        await session.flush()
        recorder.records.clear()
        yield state, session, recorder
    await state.engine.dispose()
