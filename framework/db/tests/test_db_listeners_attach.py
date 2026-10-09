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

from simple_module_db.listeners import (
    _mark_session_written,
    attach_session_listeners,
    filter_statements,
)
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


def test_attaching_twice_does_not_duplicate():
    cls = type("_AttachTwice", (Session,), {})
    attach_session_listeners(cls)
    attach_session_listeners(cls)
    assert list(cls().dispatch.after_flush).count(_mark_session_written) == 1
