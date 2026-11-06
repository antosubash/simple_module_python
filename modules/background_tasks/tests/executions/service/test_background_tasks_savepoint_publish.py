"""Unmanaged publishes respect savepoint and root outcomes (GH #729)."""

from unittest.mock import MagicMock

import pytest
from background_tasks import enqueue_after_commit
from background_tasks.core import sync_db
from sqlalchemy import text


@pytest.mark.parametrize("commit_root", [False, True])
def test_savepoint_release_waits_for_root(sync_sqlite, commit_root):
    task = MagicMock()
    factory = sync_db.get_sync_session_factory()
    with factory() as session:
        session.execute(text("CREATE TABLE effects (id INTEGER PRIMARY KEY)"))
        session.execute(text("INSERT INTO effects VALUES (1)"))
        enqueue_after_commit(session, task, "root")
        with session.begin_nested():
            with session.begin_nested():
                enqueue_after_commit(session, task, "nested")
            task.apply_async.assert_not_called()
        task.apply_async.assert_not_called()
        enqueue_after_commit(session, task, "after")
        if commit_root:
            session.commit()
        else:
            session.rollback()
        assert [call.kwargs["args"] for call in task.apply_async.call_args_list] == (
            [("root",), ("nested",), ("after",)] if commit_root else []
        )


@pytest.mark.parametrize("release_child", [False, True])
def test_savepoint_rollback_discards_only_its_publishes(sync_sqlite, release_child):
    task = MagicMock()
    factory = sync_db.get_sync_session_factory()
    with factory() as session:
        enqueue_after_commit(session, task, "root")
        with session.begin_nested() as savepoint:
            enqueue_after_commit(session, task, "rolled-back")
            if release_child:
                with session.begin_nested():
                    enqueue_after_commit(session, task, "released-child")
            savepoint.rollback()
        task.apply_async.assert_not_called()
        enqueue_after_commit(session, task, "after")
        session.commit()
        assert [call.kwargs["args"] for call in task.apply_async.call_args_list] == [
            ("root",),
            ("after",),
        ]
        # The same session must not retain callbacks from its previous transaction.
        session.commit()
        assert task.apply_async.call_count == 2
