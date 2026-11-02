"""Tenant destinations for INSERT ... SELECT (#693)."""

import pytest
from _core_scope_models import Tag, _Base, tag
from simple_module_db.listeners import attach_session_listeners
from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
from simple_module_db.tenancy import (
    TenantIsolationError,
    current_tenant_id,
    no_tenant,
    tenant_context,
)
from sqlalchemy import bindparam, create_engine, insert, literal, select, union_all
from sqlalchemy.orm import Session, configure_mappers


@pytest.fixture
def seeded():
    configure_mappers()
    engine = create_engine("sqlite://")
    _Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(tag),
            [
                {"id": 1, "name": "used", "tenant_id": "A"},
                {"id": 2, "name": "unused", "tenant_id": "A"},
                {"id": 3, "name": "b-tag", "tenant_id": "B"},
            ],
        )

    class TenantSession(Session):
        pass

    attach_session_listeners(TenantSession)
    bind_engine_policy(engine, EngineTenancy(tenant_strict=False))
    try:
        with TenantSession(engine) as session, tenant_context("A"):
            yield session
    finally:
        engine.dispose()


def _rows(session, stmt, **options):
    return sorted(session.execute(stmt.execution_options(**options)).all(), key=repr)


@pytest.mark.parametrize("compound", [False, True])
@pytest.mark.parametrize("target", [tag, Tag])
def test_insert_select_stamps_tenant_and_scopes_source(seeded, compound, target):
    source = select((tag.c.id + 100).label("id"), literal("copy").label("name"))
    if compound:
        source = union_all(source.where(tag.c.id == 1), source.where(tag.c.id == 2))
    seeded.execute(insert(target).from_select(["id", "name"], source))
    assert _rows(
        seeded, select(tag.c.id, tag.c.tenant_id).where(tag.c.id >= 100), all_tenants=True
    ) == [(101, "A"), (102, "A")]


def test_insert_select_accepts_matching_explicit_tenant(seeded):
    source = select(literal(101), literal("copy"), literal("A"))
    seeded.execute(insert(tag).from_select(["id", "name", "tenant_id"], source))
    assert _rows(seeded, select(tag.c.id).where(tag.c.id == 101)) == [(101,)]


def test_insert_select_refuses_foreign_explicit_tenant(seeded):
    source = select(literal(101), literal("copy"), literal("B"))
    with pytest.raises(TenantIsolationError):
        seeded.execute(insert(tag).from_select(["id", "name", "tenant_id"], source))


@pytest.mark.parametrize("explicit", [False, True])
def test_strict_insert_select_requires_tenant_even_for_plain_source(seeded, explicit):
    bind_engine_policy(seeded.bind, EngineTenancy(tenant_strict=True))
    current_tenant_id.set(None)
    columns, values = ["id", "name"], [literal(101), literal("copy")]
    if explicit:
        columns.append("tenant_id")
        values.append(literal("A"))
    with pytest.raises(TenantIsolationError):
        seeded.execute(insert(tag).from_select(columns, select(*values)))


def test_unbound_insert_select_uses_fallback_tenant(seeded):
    with no_tenant():
        seeded.execute(
            insert(tag).from_select(["id", "name"], select(literal(101), literal("copy")))
        )
    assert _rows(seeded, select(tag.c.tenant_id).where(tag.c.id == 101), all_tenants=True) == [
        ("default",)
    ]


@pytest.mark.parametrize("strict", [False, True])
def test_insert_select_bypass_preserves_explicit_tenant(seeded, strict):
    bind_engine_policy(seeded.bind, EngineTenancy(tenant_strict=strict))
    stmt = insert(tag).from_select(
        ["id", "name", "tenant_id"], select(literal(101), literal("copy"), literal("B"))
    )
    seeded.execute(stmt.execution_options(all_tenants=True))
    assert _rows(seeded, select(tag.c.tenant_id).where(tag.c.id == 101), all_tenants=True) == [
        ("B",)
    ]


def test_insert_select_refuses_unverifiable_tenant_expression(seeded):
    source = select(tag.c.id + 100, tag.c.name, tag.c.tenant_id)
    with pytest.raises(TenantIsolationError):
        seeded.execute(insert(tag).from_select(["id", "name", "tenant_id"], source))


def test_insert_select_checks_every_compound_branch(seeded):
    source = union_all(
        select(literal(101), literal("copy"), literal("A")),
        select(literal(102), literal("copy"), literal("B")),
    )
    with pytest.raises(TenantIsolationError):
        seeded.execute(insert(tag).from_select(["id", "name", "tenant_id"], source))


@pytest.mark.parametrize("anonymous", [False, True])
def test_insert_select_checks_execution_parameter_override(seeded, anonymous):
    tenant = literal("A") if anonymous else bindparam("tenant", "A")
    source = select(literal(101), literal("copy"), tenant)
    parameter = "param_3" if anonymous else "tenant"
    with pytest.raises(TenantIsolationError):
        seeded.execute(
            insert(tag).from_select(["id", "name", "tenant_id"], source), {parameter: "B"}
        )
