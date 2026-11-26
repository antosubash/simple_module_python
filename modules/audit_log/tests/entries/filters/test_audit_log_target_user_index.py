"""Keep correlated target-user history lookups indexed on both entity keys (#1166)."""

import uuid

from audit_log.entries.filters import EntryFilters
from audit_log.models import AuditEntry
from simple_module_core.web.audit_links import AuditLinkRegistry
from sqlalchemy import create_engine, func, select
from users.core.audit import linked_user_audit_links
from users.core.directory import UsersDirectory
from users.models import OAuthAccount


def test_target_user_count_uses_both_entity_keys():
    target = str(uuid.UUID(int=1))
    registry = AuditLinkRegistry()
    for link in linked_user_audit_links():
        registry.register(link)
    filters = EntryFilters.from_query(
        directory=UsersDirectory(), links=registry, dialect="sqlite", target_user_id=target
    )
    stmt = select(func.count()).select_from(AuditEntry).where(*filters.conditions())
    engine = create_engine("sqlite://")
    try:
        AuditEntry.__table__.create(engine)
        OAuthAccount.__table__.create(engine)
        with engine.begin() as connection:
            connection.execute(
                AuditEntry.__table__.insert(),
                [
                    {
                        "entity_type": "OAuthAccount",
                        "entity_id": str(i),
                        "action": "created",
                        "changes": [{"field": "user_id", "new": target}] if i == 0 else [],
                    }
                    for i in range(3000)
                ],
            )
            sql = str(stmt.compile(engine, compile_kwargs={"literal_binds": True}))
            plan = [row[3] for row in connection.exec_driver_sql("EXPLAIN QUERY PLAN " + sql)]
            assert any(
                "SEARCH audit_log_audit_entry_1 USING INDEX" in step
                and "(entity_type=? AND entity_id=?)" in step
                for step in plan
            ), plan
            assert connection.scalar(stmt) == 1
    finally:
        engine.dispose()
