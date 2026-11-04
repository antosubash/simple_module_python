"""The engine policy follows derived engines and per-model binds; tables register eagerly.

``engine.execution_options(...)`` gives an ``OptionEngine`` proxying the
policy's engine, and a session may be bound per model (``binds={...}``):
both keep strict mode. A model's table is known to the filters as soon as
the class is mapped, before any ORM use configures the mappers.
"""

import subprocess
import sys
import textwrap

import pytest
from _db_dml_scope_models import ScopeDoc, ScopeProj, scope_db
from simple_module_db import model_registry
from simple_module_db._engine_policies import policy_of, session_policy
from simple_module_db.query_filter import EngineTenancy, _engine_policy, bind_engine_policy
from simple_module_db.tenancy import TenantIsolationError, no_tenant, tenant_context
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

__all__ = ["scope_db"]


def _sync_class(scope_db):
    return type(scope_db.sync_session)


async def test_option_engine_keeps_strict_mode(scope_db):
    engine = scope_db.bind.execution_options(isolation_level="SERIALIZABLE")
    async with AsyncSession(engine, sync_session_class=_sync_class(scope_db)) as session:
        with no_tenant(), pytest.raises(TenantIsolationError):
            await session.execute(select(ScopeDoc))
        with tenant_context("b"):
            assert (await session.execute(select(ScopeDoc.id))).scalars().all() == [2]


async def test_per_model_binds_keep_strict_mode(scope_db):
    engine = scope_db.bind
    binds = {ScopeDoc: engine, ScopeProj: engine}
    async with AsyncSession(binds=binds, sync_session_class=_sync_class(scope_db)) as session:
        with no_tenant(), pytest.raises(TenantIsolationError):
            await session.execute(select(ScopeDoc))


async def test_connection_bound_session_keeps_strict_mode(scope_db):
    engine = scope_db.bind.execution_options(logging_token="x")
    async with engine.connect() as conn:
        session = AsyncSession(conn, sync_session_class=_sync_class(scope_db))
        with no_tenant(), pytest.raises(TenantIsolationError):
            await session.execute(select(ScopeDoc))
        await session.close()


def test_policy_lookup_resolves_through_option_engines():
    engine = create_engine("sqlite://")
    policy = EngineTenancy(tenant_strict=True)
    bind_engine_policy(engine, policy)
    derived = engine.execution_options(isolation_level="AUTOCOMMIT").execution_options(x=1)
    assert policy_of(derived) is policy
    assert _engine_policy[engine] is policy  # the map callers import is the live one
    assert session_policy(Session(binds={ScopeDoc: derived})) is policy
    assert session_policy(Session()) is None
    engine.dispose()


def test_strictest_bind_wins_for_a_session_with_several_engines():
    lax, strict = create_engine("sqlite://"), create_engine("sqlite://")
    bind_engine_policy(lax, EngineTenancy(tenant_strict=False))
    bind_engine_policy(strict, EngineTenancy(tenant_strict=True))
    session = Session(binds={ScopeProj: lax, ScopeDoc: strict})
    assert session_policy(session).tenant_strict is True
    lax.dispose()
    strict.dispose()


def test_session_overriding_get_bind_keeps_the_routed_engines_policy():
    lax, strict = create_engine("sqlite://"), create_engine("sqlite://")
    bind_engine_policy(lax, EngineTenancy(tenant_strict=False))
    bind_engine_policy(strict, EngineTenancy(tenant_strict=True))

    class RoutingSession(Session):
        def get_bind(self, mapper=None, **kwargs):
            return strict if mapper is not None and inspect(mapper).class_ is ScopeDoc else lax

    assert session_policy(RoutingSession()).tenant_strict is True
    assert session_policy(RoutingSession(bind=lax)).tenant_strict is True
    lax.dispose()
    strict.dispose()


def test_session_policy_is_memoized_per_bind():
    first, second = create_engine("sqlite://"), create_engine("sqlite://")
    bind_engine_policy(first, EngineTenancy(tenant_strict=False))
    bind_engine_policy(second, EngineTenancy(tenant_strict=True))
    session = Session(bind=first)
    assert session_policy(session).tenant_strict is False
    session.bind = second
    assert session_policy(session).tenant_strict is True
    first.dispose()
    second.dispose()


def test_policy_bound_after_a_memoized_answer_is_seen():
    engine = create_engine("sqlite://")
    session = Session(bind=engine)
    assert session_policy(session) is None
    policy = EngineTenancy(tenant_strict=True)
    bind_engine_policy(engine, policy)
    assert session_policy(session) is policy
    engine.dispose()


@pytest.mark.parametrize("bound", [True, False])
def test_unmapped_class_among_tenant_models_is_skipped(monkeypatch, bound):
    class _NotMapped:  # e.g. a model whose registry was disposed
        pass

    engine = create_engine("sqlite://")
    policy = EngineTenancy(tenant_strict=True)
    bind_engine_policy(engine, policy)
    stale = {*model_registry.tenant_classes, _NotMapped}
    monkeypatch.setattr(model_registry, "tenant_classes", stale)
    session = Session(bind=engine) if bound else Session(binds={ScopeDoc: engine})
    assert session_policy(session) is policy
    engine.dispose()


def test_session_without_a_policy_is_memoized_too():
    engine, other = create_engine("sqlite://"), create_engine("sqlite://")  # no policy bound
    calls = []

    class CountingSession(Session):
        def get_bind(self, mapper=None, **kwargs):
            calls.append(mapper)
            return self.bind

    session = CountingSession(bind=engine)
    assert session_policy(session) is None
    first = len(calls)
    assert first > 0
    assert session_policy(session) is None
    assert len(calls) == first  # the "no policy" answer was reused
    session.bind = other
    assert session_policy(session) is None
    assert len(calls) > first  # a new bind is asked again
    engine.dispose()
    other.dispose()


_EAGER_SCRIPT = textwrap.dedent(
    """
    import sqlalchemy as sa
    from sqlalchemy.orm import Session
    from sqlmodel import Field
    from simple_module_db.base import create_module_base
    from simple_module_db.listeners import attach_session_listeners
    from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
    from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
    from simple_module_db.tenancy import TenantIsolationError, tenant_context

    Base = create_module_base("eager")

    class Thing(Base, MultiTenantMixin, SoftDeleteMixin, table=True):
        __tablename__ = "eager_thing"
        id: int = Field(primary_key=True)

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    bind_engine_policy(engine, EngineTenancy(tenant_strict=True))

    class S(Session):
        pass

    attach_session_listeners(S)
    t = Thing.__table__
    with engine.begin() as c:  # Core seeding: never configures the mappers
        c.execute(sa.insert(t), [
            {"id": 1, "tenant_id": "a", "is_deleted": False},
            {"id": 2, "tenant_id": "b", "is_deleted": False},
            {"id": 3, "tenant_id": "a", "is_deleted": True},
        ])
    stmt = sa.select(t.c.id).order_by(t.c.id)
    with S(engine) as s:
        with tenant_context("a"):
            ids = list(s.execute(stmt).scalars())
        try:
            s.execute(stmt)
            raised = False
        except TenantIsolationError:
            raised = True
    print("RESULT", ids, raised)
    """
)


def test_core_statement_is_scoped_before_mappers_configure():
    # A fresh interpreter: in this one the mappers are long configured.
    proc = subprocess.run(
        [sys.executable, "-c", _EAGER_SCRIPT], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr
    assert "RESULT [1] True" in proc.stdout, proc.stdout
