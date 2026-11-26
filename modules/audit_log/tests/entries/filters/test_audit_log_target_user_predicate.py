"""Execute target predicates on SQLite without the asynchronous app fixtures."""

import uuid

import pytest
from audit_log.entries.filters import EntryFilters
from audit_log.entries.target_user import target_user_filter
from audit_log.models import AuditEntry
from simple_module_core.web.audit_links import AuditLink, AuditLinkRegistry
from sqlalchemy import create_engine, select
from users.core.audit import linked_user_audit_links
from users.core.directory import UsersDirectory
from users.models import OAuthAccount

_TARGET = uuid.UUID("11111111-1111-4111-8111-111111111111")
_OTHER = uuid.UUID("22222222-2222-4222-8222-222222222222")
_LIVE = uuid.UUID("33333333-3333-4333-8333-333333333333")
_DELETED = uuid.UUID("44444444-4444-4444-8444-444444444444")


@pytest.fixture
def audit_connection():
    engine = create_engine("sqlite://")
    AuditEntry.__table__.create(engine)
    OAuthAccount.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            OAuthAccount.__table__.insert().values(
                id=_LIVE,
                user_id=_TARGET,
                oauth_name="test",
                access_token="unused",
                account_id="live",
                account_email="test@example.com",
            )
        )
        for name, kind, entity_id, changes in [
            ("user", "User", str(_TARGET), []),
            ("live", "OAuthAccount", str(_LIVE), []),
            (
                "created-link",
                "OAuthAccount",
                str(_DELETED),
                [
                    {"field": "user_id", "new": str(_TARGET)},
                ],
            ),
            ("deleted-link", "OAuthAccount", str(_DELETED), []),
            ("role", "UserRole", str((_TARGET, _OTHER)), []),
            ("wrong-role", "UserRole", str((_OTHER, _TARGET)), []),
            ("actor-only", "User", str(_OTHER), []),
            ("wrong-kind", "Other", str(_TARGET), []),
        ]:
            connection.execute(
                AuditEntry.__table__.insert().values(
                    entity_type=kind,
                    entity_id=entity_id,
                    action=name,
                    changes=changes,
                    user_id=str(_TARGET if name == "actor-only" else _OTHER),
                )
            )
        yield connection
    engine.dispose()


def _condition(term, dialect="sqlite"):
    registry = AuditLinkRegistry()
    for link in linked_user_audit_links():
        registry.register(link)
    return target_user_filter(registry, UsersDirectory(), term, dialect)


def test_live_deleted_and_composite_ownership(audit_connection):
    stmt = select(AuditEntry.action).where(_condition(str(_TARGET)))
    assert set(audit_connection.execute(stmt).scalars()) == {
        "user",
        "live",
        "created-link",
        "deleted-link",
        "role",
    }


@pytest.mark.parametrize("term", ["not-a-uuid", str(uuid.UUID(int=0))])
def test_no_match_does_not_remove_filter(audit_connection, term):
    assert list(audit_connection.execute(select(AuditEntry.action).where(_condition(term)))) == []


def test_target_and_actor_are_independent(audit_connection):
    filters = EntryFilters(target_user_match=_condition(str(_TARGET)), user_id=str(_TARGET))
    assert (
        list(audit_connection.execute(select(AuditEntry.action).where(*filters.conditions()))) == []
    )
    actor_only = EntryFilters(user_id=str(_TARGET))
    assert list(
        audit_connection.execute(
            select(AuditEntry.action).where(*actor_only.conditions())
        ).scalars()
    ) == ["actor-only"]


def test_query_filters_combine_target_actor_entity_action_and_date(audit_connection):
    from datetime import UTC, datetime, time

    registry = AuditLinkRegistry()
    for link in linked_user_audit_links():
        registry.register(link)
    filters = EntryFilters.from_query(
        directory=UsersDirectory(),
        links=registry,
        dialect="sqlite",
        target_user_id=f" {_TARGET} ",
        user_id=f" {_OTHER} ",
        entity_type="OAuthAccount",
        action="deleted-link",
        to_date=datetime(2100, 1, 1, tzinfo=UTC),
    )
    stmt = select(AuditEntry.action).where(*filters.conditions())
    assert list(audit_connection.execute(stmt).scalars()) == ["deleted-link"]
    assert filters.to_date.time() == time.max


def test_scoped_history_cannot_supply_ownership_from_a_different_tenant(audit_connection):
    from api_tokens.models import ApiToken

    ApiToken.__table__.create(audit_connection)
    registry = AuditLinkRegistry()
    registry.register(AuditLink.for_model(ApiToken, url_template="", user_id_field="owner_user_id"))
    for tenant, owner, action in [
        ("tenant-a", _TARGET, "owned"),
        ("tenant-b", _OTHER, "other-owner"),
        ("tenant-b", None, "deleted"),
    ]:
        audit_connection.execute(
            AuditEntry.__table__.insert().values(
                entity_type="ApiToken",
                entity_id=str(_DELETED),
                action=action,
                tenant_id=tenant,
                changes=[{"field": "owner_user_id", "new": str(owner)}] if owner else [],
            )
        )
    predicate = target_user_filter(registry, UsersDirectory(), str(_TARGET), "sqlite")
    stmt = select(AuditEntry.action).where(AuditEntry.entity_type == "ApiToken", predicate)
    assert list(audit_connection.execute(stmt).scalars()) == ["owned"]


def test_whitespace_means_no_target_filter():
    assert _condition("  ") is None


def test_live_link_lookup_obeys_session_tenant_scope(audit_connection):
    from datetime import UTC, datetime

    from api_tokens.models import ApiToken
    from simple_module_db.scoping.query_filter import (
        EngineTenancy,
        bind_engine_policy,
        filter_statements,
    )
    from simple_module_db.scoping.tenancy import TenantIsolationError, no_tenant, tenant_context
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    ApiToken.__table__.create(audit_connection)
    audit_connection.execute(
        ApiToken.__table__.insert().values(
            id=_LIVE,
            owner_user_id=_TARGET,
            tenant_id="tenant-b",
            name="test",
            prefix="test",
            token_hash="unused",
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    )
    audit_connection.execute(
        AuditEntry.__table__.insert().values(
            entity_type="ApiToken",
            entity_id=str(_LIVE),
            action="live-token",
            changes=[],
            tenant_id="tenant-b",
        )
    )
    registry = AuditLinkRegistry()
    registry.register(AuditLink.for_model(ApiToken, url_template="", user_id_field="owner_user_id"))
    predicate = target_user_filter(registry, UsersDirectory(), str(_TARGET), "sqlite")
    stmt = select(AuditEntry.action).where(AuditEntry.entity_type == "ApiToken", predicate)
    bind_engine_policy(audit_connection.engine, EngineTenancy(tenant_strict=True))
    with Session(bind=audit_connection) as session:
        event.listen(session, "do_orm_execute", filter_statements)
        with no_tenant(), pytest.raises(TenantIsolationError):
            session.execute(stmt)
        with tenant_context("tenant-a"):
            assert list(session.execute(stmt).scalars()) == []
        with tenant_context("tenant-b"):
            assert list(session.execute(stmt).scalars()) == ["live-token"]


def test_postgres_predicate_compiles():
    from sqlalchemy.dialects import postgresql

    stmt = select(AuditEntry.id).where(_condition(str(_TARGET), "postgresql"))
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "jsonb_array_elements" in sql
