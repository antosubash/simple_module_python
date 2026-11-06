"""Revocations must increment the database counter rather than a stale copy."""

from sqlalchemy import event
from users.admin.queries import _UserServiceBase
from users.models import User


async def test_revocations_use_atomic_sql_and_refresh_counter(db_session):
    user = User(email="atomic@example.com", hashed_password="unused", session_version=7)
    db_session.add(user)
    await db_session.flush()
    statements = []

    def record_sql(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE"):
            statements.append(statement)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        service = _UserServiceBase(db_session, None)
        await service._revoke_sessions(user)
        # A plain read must work without implicit async IO after the flush.
        assert user.session_version == 8
        await service._revoke_sessions(user)
        assert user.session_version == 9
        await db_session.refresh(user)
        assert user.session_version == 9
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)

    # Each write derives its value from the database row, so overlapping
    # requests with the same stale value cannot overwrite an increment.
    assert len(statements) == 2
    assert all("session_version=(users_user.session_version +" in sql for sql in statements)
