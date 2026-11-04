"""Response-start finalization must preserve reads and suppress aborted work."""

from types import SimpleNamespace

import httpx
import pytest
from _models import _TxnBase, _TxnThing
from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.responses import StreamingResponse
from simple_module_db import RequestSession
from simple_module_db.deps import get_db
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from simple_module_db.transaction import CommitBeforeResponseMiddleware, finalize_session
from sqlalchemy import event, select


@pytest.fixture
async def state(tmp_path):
    state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'finalization.db'}")
    register_listeners(state)
    async with state.engine.begin() as connection:
        await connection.run_sync(_TxnBase.metadata.create_all)
    try:
        yield state
    finally:
        await state.engine.dispose()


def build_app(state):
    app = FastAPI()
    app.state.sm = SimpleNamespace(db=state)
    app.add_middleware(CommitBeforeResponseMiddleware)
    return app


@pytest.mark.parametrize("streaming", [False, True])
async def test_commit_failure_aborts_original_response(state, monkeypatch, streaming):
    app = build_app(state)
    ran = []
    real_commit = RequestSession.commit

    async def fail_once(session):
        monkeypatch.setattr(RequestSession, "commit", real_commit)
        raise RuntimeError("commit failed")

    monkeypatch.setattr(RequestSession, "commit", fail_once)

    @app.post("/")
    async def endpoint(bg: BackgroundTasks, db: RequestSession = Depends(get_db)):
        db.add(_TxnThing(name="endpoint"))
        await db.flush()

        async def write(name):
            ran.append(name)
            db.add(_TxnThing(name=name))
            await db.flush()

        async def body():
            await write("stream")
            yield b"original"

        bg.add_task(write, "background")
        return StreamingResponse(body(), background=bg) if streaming else {}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert ran == []
    async with state.session_factory() as db:
        assert (await db.execute(select(_TxnThing))).scalars().all() == []


async def test_read_only_response_keeps_loaded_attributes_and_releases_connection(state):
    async with state.session_factory() as db:
        db.add(_TxnThing(name="hello"))
        await db.commit()
    app = build_app(state)
    observed = []
    checked_out = []
    event.listen(state.engine.sync_engine, "checkout", lambda *args: checked_out.append(1))
    event.listen(state.engine.sync_engine, "checkin", lambda *args: checked_out.pop())

    @app.get("/")
    async def endpoint(bg: BackgroundTasks, db: RequestSession = Depends(get_db)):
        row = (await db.execute(select(_TxnThing))).scalar_one()

        async def task():
            observed.append(row.name)
            row.name = "updated in background"
            await db.flush()

        async def body():
            assert checked_out == []
            assert not db.in_transaction()
            yield row.name.encode()

        bg.add_task(task)
        return StreamingResponse(body(), background=bg)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")
    assert response.content == b"hello"
    assert observed == ["hello"]
    async with state.session_factory() as db:
        assert (await db.execute(select(_TxnThing.name))).scalar_one() == "updated in background"


@pytest.mark.parametrize("write_kind", ["orm", "dml", "raw"])
@pytest.mark.parametrize("outer_write", [False, True])
async def test_savepoint_rollback_only_discards_its_write_marker(state, write_kind, outer_write):
    from simple_module_db import mark_written
    from sqlalchemy import insert, text

    observed = []
    async with state.session_factory() as db:
        db.on_commit(lambda: observed.append("outer"))
        if outer_write:
            db.add(_TxnThing(name="kept"))
            await db.flush()
        with pytest.raises(ValueError):
            async with db.begin_nested():
                db.on_commit(lambda: observed.append("rolled back"))
                if write_kind == "orm":
                    db.add(_TxnThing(name="gone"))
                    await db.flush()
                elif write_kind == "dml":
                    await db.execute(insert(_TxnThing).values(name="gone"))
                else:
                    await db.execute(text("INSERT INTO txn_test_thing (name) VALUES ('gone')"))
                    mark_written(db)
                raise ValueError("abort savepoint")
        await finalize_session(db)
    assert observed == (["outer"] if outer_write else [])
    async with state.session_factory() as db:
        assert (await db.execute(select(_TxnThing.name))).scalars().all() == (
            ["kept"] if outer_write else []
        )


@pytest.mark.parametrize("rollback_parent", [False, True])
async def test_released_child_write_belongs_to_parent_savepoint(state, rollback_parent):
    observed = []
    async with state.session_factory() as db:
        db.on_commit(lambda: observed.append("outer"))
        parent = await db.begin_nested()
        async with db.begin_nested():
            db.add(_TxnThing(name="child"))
            await db.flush()
            db.on_commit(lambda: observed.append("child"))
        if rollback_parent:
            await parent.rollback()
        else:
            await parent.commit()
        await finalize_session(db)
    assert observed == ([] if rollback_parent else ["outer", "child"])
    async with state.session_factory() as db:
        assert (await db.execute(select(_TxnThing.name))).scalars().all() == (
            [] if rollback_parent else ["child"]
        )
