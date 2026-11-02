"""Connection-bound sessions retain their engine's tenancy and audit policy (#630)."""

from collections.abc import Iterator

import pytest
from _audit_models import AuditTestItem
from _models import _TenantItem
from simple_module_db.audit import AuditRecord
from simple_module_db.listeners import attach_session_listeners
from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
from simple_module_db.tenancy import TenantIsolationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def connection_session() -> Iterator[tuple[Session, list[AuditRecord]]]:
    engine = create_engine("sqlite://")
    records: list[AuditRecord] = []

    def capture(session: Session, changes: list[AuditRecord]) -> None:
        records.extend(changes)

    class ConnectionSession(Session):
        pass

    attach_session_listeners(ConnectionSession)
    bind_engine_policy(engine, EngineTenancy(tenant_strict=True, audit_callback=capture))
    try:
        _TenantItem.__table__.create(engine)
        AuditTestItem.__table__.create(engine)
        with engine.begin() as connection:
            connection.execute(
                _TenantItem.__table__.insert(),
                [{"name": "row-a", "tenant_id": "a"}, {"name": "row-b", "tenant_id": "b"}],
            )
        with engine.connect() as connection, ConnectionSession(bind=connection) as session:
            yield session, records
    finally:
        engine.dispose()


def test_connection_bound_select_without_tenant_fails_closed(connection_session):
    session, _records = connection_session
    with pytest.raises(TenantIsolationError):
        session.execute(select(_TenantItem)).all()


def test_connection_bound_flush_without_tenant_fails_closed(connection_session):
    session, _records = connection_session
    session.add(_TenantItem(name="missing-tenant"))
    with pytest.raises(TenantIsolationError):
        session.flush()


def test_connection_bound_flush_delivers_audit_records(connection_session):
    session, records = connection_session
    item = AuditTestItem(name="audited")
    session.add(item)
    session.flush()

    [record] = records
    assert (record.entity_type, record.action, record.entity_id) == (
        "AuditTestItem",
        "created",
        str(item.id),
    )
