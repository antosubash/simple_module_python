"""Unsupported dialects must fail before either worker engine is constructed."""

import pytest
from background_tasks.core import sync_db
from background_tasks.outbox import worker


@pytest.mark.parametrize("dialect", ["mysql+aiomysql", "mssql+pyodbc"])
@pytest.mark.parametrize("async_worker", [False, True], ids=["sync", "outbox"])
def test_worker_rejects_unknown_dialect(monkeypatch, dialect, async_worker):
    monkeypatch.setattr(sync_db, "_url_override", f"{dialect}://user:hidden-password@host/db")
    with pytest.raises(ValueError) as error:
        if async_worker:
            worker.worker_session_factory()
        else:
            sync_db._build_engine()
    assert dialect.split("+")[0] in str(error.value)
    assert "hidden-password" not in str(error.value)
