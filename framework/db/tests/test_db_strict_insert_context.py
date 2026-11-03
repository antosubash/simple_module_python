"""Strict inserts require context even when every row names an owner (#728)."""

import pytest
from _models import _TenantBase, _TenantItem
from simple_module_db import all_tenants, no_tenant, tenant_context
from simple_module_db.listeners import attach_session_listeners
from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
from simple_module_db.tenancy import MissingTenantError, TenantIsolationError
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session


@pytest.fixture
def strict_session():
    engine = create_engine("sqlite://")
    _TenantBase.metadata.create_all(engine)

    class TenantSession(Session):
        pass

    attach_session_listeners(TenantSession)
    bind_engine_policy(engine, EngineTenancy(tenant_strict=True))
    try:
        with TenantSession(engine) as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture(params=["orm", "values", "parameters", "multi_values"])
def form(request):
    return request.param


def _insert(session, form, owner, *, bypass=False):
    payload = {"name": "inserted"}
    if owner is not None:
        payload["tenant_id"] = owner
    if form == "orm":
        session.add(_TenantItem(**payload))
        session.flush()
        return
    stmt = insert(_TenantItem)
    if bypass:
        stmt = stmt.execution_options(all_tenants=True)
    if form == "parameters":
        session.execute(stmt, [payload])
    elif form == "multi_values":
        session.execute(stmt.values([payload]))
    else:
        session.execute(stmt.values(**payload))


@pytest.mark.parametrize("owner", [None, "victim"])
def test_unbound_strict_insert_raises_missing_tenant(strict_session, form, owner):
    with no_tenant(), pytest.raises(MissingTenantError, match="INSERT"):
        _insert(strict_session, form, owner)
    strict_session.rollback()
    with all_tenants():
        assert (strict_session.execute(select(_TenantItem))).scalars().all() == []


def test_bound_strict_insert_rejects_foreign_owner(strict_session, form):
    with tenant_context("actor"), pytest.raises(TenantIsolationError):
        _insert(strict_session, form, "victim")
    strict_session.rollback()


@pytest.mark.parametrize("owner", [None, "actor"])
def test_bound_strict_insert_uses_matching_owner(strict_session, form, owner):
    with tenant_context("actor"):
        _insert(strict_session, form, owner)
        strict_session.commit()
        row = (strict_session.execute(select(_TenantItem))).scalar_one()
        assert row.tenant_id == "actor"


def test_strict_insert_allows_explicit_cross_tenant_block(strict_session, form):
    with all_tenants():
        _insert(strict_session, form, "victim")
        strict_session.commit()
        row = (strict_session.execute(select(_TenantItem))).scalar_one()
        assert row.tenant_id == "victim"


@pytest.mark.parametrize("form", ["values", "parameters", "multi_values"])
def test_strict_insert_allows_statement_bypass(strict_session, form):
    with no_tenant():
        _insert(strict_session, form, "victim", bypass=True)
        strict_session.commit()
    with all_tenants():
        row = (strict_session.execute(select(_TenantItem))).scalar_one()
        assert row.tenant_id == "victim"


@pytest.mark.parametrize(("owner", "expected"), [(None, "default"), ("victim", "victim")])
def test_non_strict_unbound_insert_preserves_owner_or_uses_fallback(
    strict_session, form, owner, expected
):
    bind_engine_policy(strict_session.bind, EngineTenancy(tenant_strict=False))
    with no_tenant():
        _insert(strict_session, form, owner)
        strict_session.commit()
        row = strict_session.execute(select(_TenantItem)).scalar_one()
        assert row.tenant_id == expected
