"""Tests for commit-before-response (GH #257).

A client that creates a row and immediately references it by id used to get a
deterministic 404: FastAPI runs a ``yield`` dependency's exit code *after* the
response is delivered, so the create's ``201`` beat the create's commit and the
follow-up request opened a fresh session that saw nothing.

These use a **file-backed** SQLite database on purpose. An in-memory SQLite URL
shares one connection across every session, which makes uncommitted writes
visible to the "second request" and hides the very race under test.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace

import httpx
import pytest
from _models import _TxnBase, _TxnThing
from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.responses import StreamingResponse
from simple_module_db.deps import get_db
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from simple_module_db.transaction import CommitBeforeResponseMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


def _build_app(db_state, *, with_middleware: bool = True) -> FastAPI:
    """A miniature host: create flushes only, read opens its own session."""
    app = FastAPI()
    if with_middleware:
        app.add_middleware(CommitBeforeResponseMiddleware)
    app.state.sm = SimpleNamespace(db=db_state)

    @app.post("/things", status_code=201)
    async def create(name: str, db: AsyncSession = Depends(get_db)):
        # Deliberately no commit() — get_db owns the unit of work, which is
        # exactly the pattern the framework documents for service code.
        thing = _TxnThing(name=name)
        db.add(thing)
        await db.flush()
        return {"id": thing.id}

    @app.get("/things/{thing_id}")
    async def read(thing_id: int, db: AsyncSession = Depends(get_db)):
        found = (
            await db.execute(select(_TxnThing).where(_TxnThing.id == thing_id))
        ).scalar_one_or_none()
        if found is None:
            return {"found": False}
        return {"found": True, "name": found.name}

    @app.post("/boom", status_code=201)
    async def boom(db: AsyncSession = Depends(get_db)):
        db.add(_TxnThing(name="doomed"))
        await db.flush()
        raise RuntimeError("endpoint blew up after writing")

    return app


@pytest.fixture
async def db_state(tmp_path) -> AsyncGenerator[object, None]:
    state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'txn.db'}")
    try:
        # The after_flush listener is what marks a session as having writes
        # once flush() has emptied new/dirty/deleted — create_app registers it,
        # so the fixture must too or every request looks read-only.
        register_listeners(state)
        async with state.engine.begin() as conn:
            await conn.run_sync(_TxnBase.metadata.create_all)
        yield state
    finally:
        await state.engine.dispose()


async def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


class TestCommitBeforeResponse:
    async def test_created_row_is_readable_on_the_very_next_request(self, db_state):
        """The client-visible contract: no second pass, no retry loop.

        Note this one does *not* fail without the fix — httpx's in-process ASGI
        transport awaits the whole request, teardown included, before issuing
        the next one, so the follow-up can never beat the commit here. It
        documents the intended behaviour; the ordering guarantee is pinned by
        ``test_write_is_durable_before_the_response_is_delivered`` below, which
        does fail without the middleware.
        """
        async with await _client(_build_app(db_state)) as client:
            created = await client.post("/things", params={"name": "page-1"})
            assert created.status_code == 201
            thing_id = created.json()["id"]

            found = await client.get(f"/things/{thing_id}")

        assert found.json() == {"found": True, "name": "page-1"}

    async def test_write_is_durable_before_the_response_is_delivered(self, db_state):
        """Stronger than the round-trip above: assert against a connection that
        the request never touched, at the moment the response is emitted."""
        app = _build_app(db_state)
        visible_at_response_start: list[bool] = []

        class Probe:
            def __init__(self, inner):
                self.inner = inner

            async def __call__(self, scope, receive, send):
                async def spy(message):
                    if message["type"] == "http.response.start":
                        async with db_state.session_factory() as other:
                            rows = (await other.execute(select(_TxnThing))).scalars().all()
                            visible_at_response_start.append(bool(rows))
                    await send(message)

                await self.inner(scope, receive, spy)

        async with await _client(Probe(app)) as client:
            assert (await client.post("/things", params={"name": "durable"})).status_code == 201

        assert visible_at_response_start == [True], (
            "row was not committed by the time the response left the server"
        )

    async def test_endpoint_exception_still_rolls_back(self, db_state):
        """The middleware must not turn a failed request's writes into a commit."""
        async with await _client(_build_app(db_state)) as client:
            assert (await client.post("/boom")).status_code == 500

        async with db_state.session_factory() as session:
            assert (await session.execute(select(_TxnThing))).scalars().all() == []

    async def test_commit_failure_becomes_a_500_and_persists_nothing(self, db_state, monkeypatch):
        """A commit that blows up at response.start replaces the response rather
        than shipping a 201 for work that never landed.

        The failure is injected at ``AsyncSession.commit`` rather than at
        ``finalize_session``: stubbing the finalizer would bypass its bookkeeping,
        leaving get_db's fallback free to commit the row the test claims was
        lost — the assertion would pass while the guarantee was broken.
        """

        async def explode(self, *args, **kwargs):
            raise RuntimeError("commit failed")

        monkeypatch.setattr(AsyncSession, "commit", explode)

        async with await _client(_build_app(db_state)) as client:
            response = await client.post("/things", params={"name": "nope"})

        assert response.status_code == 500
        assert response.json() == {"detail": "Internal Server Error"}

        monkeypatch.undo()
        async with db_state.session_factory() as session:
            assert (await session.execute(select(_TxnThing))).scalars().all() == []

    async def test_background_task_writes_still_commit(self, db_state):
        """Starlette runs BackgroundTasks after the body is sent, on this same
        session. Finalizing at response.start must not consume the session and
        strand them — they flushed but never committed, losing writes silently."""
        app = _build_app(db_state)

        @app.post("/with-task", status_code=202)
        async def with_task(bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
            db.add(_TxnThing(name="before-response"))
            await db.flush()

            async def task():
                db.add(_TxnThing(name="from-background-task"))
                await db.flush()

            bg.add_task(task)
            return {"ok": True}

        async with await _client(app) as client:
            assert (await client.post("/with-task")).status_code == 202

        async with db_state.session_factory() as session:
            names = sorted(t.name for t in (await session.execute(select(_TxnThing))).scalars())
        assert names == ["before-response", "from-background-task"]

    async def test_streaming_response_body_writes_still_commit(self, db_state):
        """A StreamingResponse writes its body *after* response.start, so work
        done while streaming lands after the middleware's commit."""
        app = _build_app(db_state)

        @app.get("/stream")
        async def stream(db: AsyncSession = Depends(get_db)):
            db.add(_TxnThing(name="before-stream"))
            await db.flush()

            async def body():
                yield b"chunk"
                db.add(_TxnThing(name="during-stream"))
                await db.flush()

            return StreamingResponse(body())

        async with await _client(app) as client:
            assert (await client.get("/stream")).status_code == 200

        async with db_state.session_factory() as session:
            names = sorted(t.name for t in (await session.execute(select(_TxnThing))).scalars())
        assert names == ["before-stream", "during-stream"]

    async def test_still_commits_without_the_middleware(self, db_state):
        """get_db keeps its own fallback finalize, so the dependency works
        standalone — in a WebSocket handler, or a test that builds no stack."""
        app = _build_app(db_state, with_middleware=False)
        async with await _client(app) as client:
            assert (await client.post("/things", params={"name": "solo"})).status_code == 201

        async with db_state.session_factory() as session:
            names = [t.name for t in (await session.execute(select(_TxnThing))).scalars().all()]
        assert names == ["solo"]

    async def test_read_only_request_is_not_committed(self, db_state):
        """Read-only handlers still exit via rollback — one round-trip cheaper."""
        app = _build_app(db_state)
        async with await _client(app) as client:
            assert (await client.get("/things/999")).json() == {"found": False}
