"""The worker's sync session enforces the tenant restored around a task body (#371)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from background_tasks import sync_db
from background_tasks.tenant_context import TENANT_HEADER, release_tenant, restore_tenant
from simple_module_db import (
    DEFAULT_TENANT_ID,
    MultiTenantMixin,
    TenantIsolationError,
    all_tenants,
    create_module_base,
)
from sqlalchemy import create_engine, select
from sqlmodel import Field

_Base = create_module_base("bgtenancy")


class _Job(_Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "bgtenancy_job"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=50)


@pytest.fixture
def worker_db(tmp_path):
    url = f"sqlite:///{tmp_path}/worker.db"
    _Base.metadata.create_all(create_engine(url))
    sync_db.set_database_url(url, tenant_strict=True)
    with sync_db.sync_session() as s:
        s.add_all([_Job(name="a1", tenant_id="a"), _Job(name="b1", tenant_id="b")])
    yield
    sync_db.dispose_sync_engine()


def _task(tenant: str) -> SimpleNamespace:
    return SimpleNamespace(request=SimpleNamespace(**{TENANT_HEADER: tenant}))


def test_task_body_sees_only_its_tenant(worker_db):
    restore_tenant(task_id="t1", task=_task("a"))
    try:
        with sync_db.sync_session() as s:
            assert s.scalars(select(_Job.name)).all() == ["a1"]
    finally:
        release_tenant(task_id="t1")


def test_task_body_cannot_write_another_tenant(worker_db):
    restore_tenant(task_id="t2", task=_task("a"))
    try:
        with pytest.raises(TenantIsolationError), sync_db.sync_session() as s:
            s.add(_Job(name="planted", tenant_id="b"))
    finally:
        release_tenant(task_id="t2")


def test_task_without_a_tenant_fails_closed(worker_db):
    with pytest.raises(TenantIsolationError), sync_db.sync_session() as s:
        s.execute(select(_Job))


def _fresh(tmp_path, name: str, **policy) -> None:
    url = f"sqlite:///{tmp_path}/{name}.db"
    _Base.metadata.create_all(create_engine(url))
    sync_db.set_database_url(url, **policy)


def test_unbound_insert_lands_in_the_default_tenant(tmp_path):
    """A ``default_tenant`` install's worker stamps an ``all_tenants()`` insert
    with it — as ``DatabaseState.default_tenant_id`` does in the web process."""
    _fresh(tmp_path, "default", tenant_strict=False, default_tenant="main")
    try:
        with all_tenants(), sync_db.sync_session() as s:
            s.add(_Job(name="swept"))
        with sync_db.sync_session() as s:
            assert s.scalars(select(_Job.tenant_id)).all() == ["main"]
    finally:
        sync_db.dispose_sync_engine()


def test_without_default_tenant_the_constant_is_used(tmp_path):
    _fresh(tmp_path, "constant", tenant_strict=False)
    try:
        with all_tenants(), sync_db.sync_session() as s:
            s.add(_Job(name="swept"))
        with sync_db.sync_session() as s:
            assert s.scalars(select(_Job.tenant_id)).all() == [DEFAULT_TENANT_ID]
    finally:
        sync_db.dispose_sync_engine()


def test_default_tenant_is_ignored_when_strict(tmp_path):
    _fresh(tmp_path, "strict", tenant_strict=True, default_tenant="main")
    try:
        from simple_module_db.query_filter import _engine_policy

        sync_db.get_sync_session_factory()
        policy = _engine_policy[sync_db._engine]
        assert policy.tenant_strict
        assert policy.default_tenant_id == DEFAULT_TENANT_ID
    finally:
        sync_db.dispose_sync_engine()
