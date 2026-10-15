"""Shared helpers for the file_storage suite.

``recorded_statements`` is the tool the performance tests are written with:
this module's cost problem is *how many* queries a screen issues, not how long
they take, so the assertions count statements rather than milliseconds. A
wall-clock budget would be the flakiest check in CI and would still pass on the
day someone adds a fourth full-table scan to a fast machine.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine


@pytest.fixture
def record_statements():
    """Yield a context manager recording SQL issued against an engine.

    Takes the app or engine to watch and returns a growing list of normalised
    statement texts, so a test can filter for the ones naming a table it cares
    about.
    """

    @contextlib.contextmanager
    def _watch(target) -> Generator[list[str]]:
        engine = _sync_engine(target)
        seen: list[str] = []

        def _record(conn, cursor, statement, parameters, context, executemany) -> None:
            seen.append(" ".join(statement.split()))

        event.listen(engine, "before_cursor_execute", _record)
        try:
            yield seen
        finally:
            event.remove(engine, "before_cursor_execute", _record)

    return _watch


def _sync_engine(target) -> Engine:
    """Accept an app, an ``AsyncEngine`` or a sync ``Engine`` interchangeably."""
    engine = target.state.sm.db.engine if hasattr(target, "state") else target
    return getattr(engine, "sync_engine", engine)


@pytest.fixture
async def admin_tenant_id(app) -> str:
    """Give the seeded admin an organisation it owns; that tenant's id.

    ``StoredFile`` is tenant-scoped and the suite runs strict, so a request
    with no active tenant fails closed (403 ``tenant_required``). The tenants
    resolver falls back to a user's first membership, so one membership is
    enough to make every ``authenticated_client`` request act for this tenant.
    """
    from simple_module_test.fixtures import SETUP_ADMIN_EMAIL
    from sqlalchemy import select
    from tenants.models import Membership, Tenant
    from tenants.resolver import forget
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        admin = (
            await session.execute(select(User).where(User.email == SETUP_ADMIN_EMAIL))
        ).scalar_one()
        tenant = Tenant(slug="admin-org", name="Admin Org")
        session.add(tenant)
        await session.flush()
        session.add(
            Membership(tenant_id=tenant.id, user_id=str(admin.id), role="owner", email=admin.email)
        )
        await session.commit()
        forget(str(admin.id))
        return tenant.id


@pytest.fixture
async def authenticated_client(authenticated_client, admin_tenant_id):
    """The plugin's admin client, acting for the admin's own organisation."""
    return authenticated_client


@pytest.fixture
def checksum_calls(monkeypatch) -> list[tuple]:
    """Capture ``enqueue_after_commit`` instead of running the (eager) task.

    The test Celery app is eager, so an enqueue would run
    ``file_storage.compute_checksum`` inline against whichever database the
    worker-side sync engine points at. The task is exercised on its own in
    ``test_file_storage_upload_tasks``; request tests only need to see that it
    was asked for.
    """
    import background_tasks

    calls: list[tuple] = []
    monkeypatch.setattr(
        background_tasks, "enqueue_after_commit", lambda db, task, *a, **kw: calls.append((task, a))
    )
    return calls
