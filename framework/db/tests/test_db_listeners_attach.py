"""``attach_session_listeners`` wires every fresh session class (#417 follow-up).

SQLAlchemy keys its event registry on ``id(target)``. ``event.contains`` on a
new session class that reuses a garbage-collected class's id reports the dead
class's listeners, so an ``event.contains`` guard skipped wiring the new class
entirely: no tenant stamping, no tenant/soft-delete filter, no write marker.
That surfaced as an order-dependent test failure (a request's write never
committed) once enough ``init_db`` session classes had come and gone.
"""

from __future__ import annotations

import gc

import pytest
from _models import _TenantItem
from simple_module_db.listeners import (
    _LISTENERS_ATTACHED,
    TenantIsolationError,
    _mark_session_written,
    attach_session_listeners,
    filter_statements,
)
from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
from simple_module_db.tenancy import tenant_context
from simple_module_db.writes import SESSION_HAS_WRITES_KEY
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def test_every_fresh_session_class_gets_the_listeners():
    for i in range(50):
        cls = type(f"_AttachProbe{i}", (Session,), {})
        attach_session_listeners(cls)
        session = cls()
        assert _mark_session_written in list(session.dispatch.after_flush), i
        assert filter_statements in list(session.dispatch.do_orm_execute), i
        session.close()
        del cls, session
        gc.collect()


def test_subclass_of_a_wired_class_inherits_the_listeners_once():
    """The MRO guard skips wiring a subclass; it must still be filtered.

    SQLAlchemy propagates class-level session listeners to subclasses, including
    ones defined after the parent was wired, so the subclass is isolated by
    tenant and fails closed - and a second wiring would fire everything twice.
    """
    parent = type("_AttachParent", (Session,), {})
    attach_session_listeners(parent)
    child = type("_AttachChild", (parent,), {})
    attach_session_listeners(child)
    assert _LISTENERS_ATTACHED not in child.__dict__

    engine = create_engine("sqlite://")
    _TenantItem.__table__.create(engine)
    bind_engine_policy(engine, EngineTenancy(tenant_strict=True))
    try:
        for tenant in ("a", "b"):
            with tenant_context(tenant), child(engine) as session:
                session.add(_TenantItem(name=f"row-{tenant}"))
                session.flush()
                assert session.info.get(SESSION_HAS_WRITES_KEY) is True
                assert list(session.dispatch.after_flush).count(_mark_session_written) == 1
                assert list(session.dispatch.do_orm_execute).count(filter_statements) == 1
                session.commit()

        with tenant_context("a"), child(engine) as session:
            rows = session.execute(select(_TenantItem)).scalars().all()
            assert [(r.name, r.tenant_id) for r in rows] == [("row-a", "a")]

        with child(engine) as session, pytest.raises(TenantIsolationError):
            session.execute(select(_TenantItem)).all()
    finally:
        engine.dispose()


def test_attaching_twice_does_not_duplicate():
    cls = type("_AttachTwice", (Session,), {})
    attach_session_listeners(cls)
    attach_session_listeners(cls)
    assert list(cls().dispatch.after_flush).count(_mark_session_written) == 1
