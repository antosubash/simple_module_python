"""Absolute refresh-family age bounds retained rotation history (#656)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from users.auth_local.token_api import RefreshRequest, TokenResponse, token_refresh
from users.db_adapter import get_access_token_db
from users.models import Base, RefreshToken, User, UserAccessToken
from users.settings import UsersSettings
from users.token_storage import hash_token, prune_tokens


@pytest.fixture
def family_db():
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            owner = uuid.uuid4()
            session.add(User(id=owner, email="family@example.com"))
            session.flush()
            yield session, owner
    finally:
        engine.dispose()


class _AsyncSession:
    def __init__(self, session):
        self.session = session

    def add(self, row):
        self.session.add(row)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def refresh(self, row):
        self.session.refresh(row)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def execute(self, statement):
        return self.session.execute(statement)


def _family(session, owner, now, age_days, *, children=1):
    family = uuid.uuid4()
    session.add(
        RefreshToken(
            token=str(uuid.uuid4()),
            user_id=owner,
            family_id=family,
            created_at=now - timedelta(days=age_days),
            expires_at=now - timedelta(days=1),
            revoked_at=now - timedelta(days=1),
        )
    )
    secrets = [str(uuid.uuid4()) for _ in range(children)]
    for secret in secrets:
        session.add(
            RefreshToken(
                token=hash_token(secret),
                user_id=owner,
                family_id=family,
                created_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
    session.flush()
    return secrets


@pytest.mark.parametrize("age_days", [7, 8, 91])
@pytest.mark.parametrize("expired", [False, True])
def test_users_refresh_refuses_old_family_and_revokes_all_live_children(
    family_db, expired, age_days
):
    session, owner = family_db
    now = datetime.now(UTC)
    secrets = _family(session, owner, now, age_days, children=2)
    if expired:
        session.get(RefreshToken, hash_token(secrets[0])).expires_at = now - timedelta(seconds=1)
        session.flush()
    settings = (
        UsersSettings() if age_days == 91 else UsersSettings(refresh_token_family_max_age_days=7)
    )
    request = _request(settings)
    response = asyncio.run(
        token_refresh(RefreshRequest(refresh_token=secrets[0]), request, _AsyncSession(session))
    )
    assert isinstance(response, JSONResponse)
    assert response.status_code == 401
    session.expire_all()
    assert all(row.revoked_at is not None for row in session.scalars(sa.select(RefreshToken)))
    assert session.scalar(sa.select(sa.func.count()).select_from(UserAccessToken)) == 0


def test_users_prune_revokes_old_family_before_bounded_deletion(family_db):
    session, owner = family_db
    now = datetime.now(UTC)
    _family(session, owner, now, 8, children=101)
    recent = _family(session, owner, now, 6)
    other = uuid.uuid4()
    session.add(User(id=other, email="other@example.com"))
    session.flush()
    other_old = _family(session, other, now, 8)

    for _ in range(2):
        asyncio.run(prune_tokens(_AsyncSession(session), owner, now, family_max_age_days=7))
        session.expire_all()
        # Even if the oldest ancestor was in the first batch, no child becomes live again.
        remaining = list(
            session.scalars(
                sa.select(RefreshToken).where(
                    RefreshToken.user_id == owner, RefreshToken.token != hash_token(recent[0])
                )
            )
        )
        assert all(row.revoked_at is not None for row in remaining)
    assert session.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 4
    assert session.get(RefreshToken, hash_token(recent[0])).revoked_at is None
    assert session.get(RefreshToken, hash_token(other_old[0])).revoked_at is None


def test_users_family_max_age_rejects_zero():
    with pytest.raises(ValidationError):
        UsersSettings(refresh_token_family_max_age_days=0)


def _request(settings):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(users=SimpleNamespace(settings=settings, demo_user_ids=set()))
        )
    )


def test_users_recent_family_rotates_and_keeps_expired_ancestor_reuse_evidence(family_db):
    session, owner = family_db
    now = datetime.now(UTC)
    secrets = _family(session, owner, now, 6)
    ancestor = session.scalar(sa.select(RefreshToken).where(RefreshToken.revoked_at.is_not(None)))
    ancestor_secret = str(uuid.uuid4())
    ancestor.token = hash_token(ancestor_secret)
    session.flush()
    request = _request(UsersSettings(refresh_token_family_max_age_days=7))
    db = _AsyncSession(session)
    rotated = asyncio.run(token_refresh(RefreshRequest(refresh_token=secrets[0]), request, db))
    assert isinstance(rotated, TokenResponse)
    assert session.get(RefreshToken, hash_token(ancestor_secret)) is not None
    for secret in (ancestor_secret, rotated.refresh_token):
        refused = asyncio.run(token_refresh(RefreshRequest(refresh_token=secret), request, db))
        assert refused.status_code == 401


def test_users_cookie_cleanup_uses_configured_family_max_age(family_db):
    session, owner = family_db
    now = datetime.now(UTC)
    _family(session, owner, now, 8)
    request = _request(UsersSettings(refresh_token_family_max_age_days=7))

    async def login():
        async for database in get_access_token_db(request, _AsyncSession(session)):
            await database.create({"token": "cookie", "user_id": owner})

    asyncio.run(login())
    assert session.scalar(sa.select(sa.func.count()).select_from(RefreshToken)) == 0
