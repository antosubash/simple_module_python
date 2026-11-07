"""``expires_at`` round-trips as aware UTC on SQLite and uses AwareDateTime (GH #869)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from simple_module_db.types import AwareDateTime
from sqlalchemy import select
from users.models import User, UserAccessToken


def test_expires_at_column_type_is_aware_datetime():
    assert isinstance(UserAccessToken.__table__.c.expires_at.type, AwareDateTime)


@pytest.mark.anyio
async def test_expires_at_round_trips_aware_utc(db_session):
    user_id = uuid.uuid4()
    db_session.add(
        User(
            id=user_id,
            email="expires@example.com",
            hashed_password="hashed",
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
    )
    await db_session.commit()
    expires = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1)
    db_session.add(UserAccessToken(token="b" * 43, user_id=user_id, expires_at=expires))
    await db_session.commit()
    db_session.expire_all()

    row = (await db_session.execute(select(UserAccessToken))).scalar_one()
    assert row.expires_at.tzinfo is not None
    assert row.expires_at.utcoffset() == timedelta(0)
    assert row.expires_at == expires
