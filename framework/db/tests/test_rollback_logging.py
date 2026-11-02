"""Only rollbacks that discard writes warrant a warning."""

import logging

import pytest
from _models import _TxnThing
from simple_module_db import mark_written
from simple_module_db.transaction import rollback_session
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.parametrize("pending", ["none", "new", "written"])
async def test_rollback_log_level_matches_pending_work(caplog, pending):
    async with AsyncSession() as session:
        if pending == "new":
            session.add(_TxnThing(name="discarded"))
        elif pending == "written":
            mark_written(session)
        with caplog.at_level(logging.DEBUG, logger="simple_module.db"):
            await rollback_session(session)
    records = [record for record in caplog.records if record.message == "db.session.rollback"]
    assert len(records) == 1
    assert records[0].levelno == (logging.DEBUG if pending == "none" else logging.WARNING)
