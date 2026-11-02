"""User deletion purges personal tokens across tenants transactionally (#657)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from api_tokens.constants import TokenKind
from api_tokens.models import ApiToken
from api_tokens.module import ApiTokensModule
from simple_module_core.events import EventBus
from simple_module_core.user_events import UserDeleted
from simple_module_db import all_tenants, tenant_context
from simple_module_db.transaction import finalize_session, rollback_session
from sqlmodel import select


@pytest.mark.parametrize("rollback", [False, True])
async def test_api_tokens_user_deleted_cleanup_is_scoped_idempotent_and_transactional(
    db_session, rollback
):
    deleted_id, other_id = uuid.uuid4(), uuid.uuid4()
    kept_ids = set()
    for tenant_id in ("first", "second"):
        with tenant_context(tenant_id):
            for kind, owner in (
                (TokenKind.PERSONAL, deleted_id),
                (TokenKind.PERSONAL, other_id),
                (TokenKind.SERVICE, deleted_id),
            ):
                token = ApiToken(
                    kind=kind,
                    owner_user_id=owner,
                    name="token",
                    prefix="test",
                    token_hash=uuid.uuid4().hex,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
                db_session.add(token)
                if kind == TokenKind.SERVICE or owner == other_id:
                    kept_ids.add(token.id)
            await db_session.flush()
    await finalize_session(db_session)
    bus = EventBus()
    # Workers register without an app; inline delivery uses the same durable subscription.
    ApiTokensModule().register_event_handlers(bus)
    with tenant_context("first"):
        for _ in range(2):
            await bus.publish_durable_or_inline(UserDeleted(deleted_id), db_session)
    with all_tenants():
        remaining = (await db_session.execute(select(ApiToken.id))).scalars().all()
    assert set(remaining) == kept_ids
    if rollback:
        await rollback_session(db_session)
    else:
        await finalize_session(db_session)
    with all_tenants():
        remaining = (await db_session.execute(select(ApiToken.id))).scalars().all()
    if rollback:
        assert len(remaining) == 6
    else:
        assert set(remaining) == kept_ids
