"""Exercise bounded pruning SQL without the async SQLite driver (#626)."""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy.orm import Session
from users.models import RefreshToken, UserAccessToken
from users.token_storage import prune_tokens


def test_users_pruning_is_bounded_scoped_and_keeps_active_family_evidence():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    users = sa.Table("users_user", metadata, sa.Column("id", GUID(), primary_key=True))
    refresh = RefreshToken.__table__.to_metadata(metadata)
    access = UserAccessToken.__table__.to_metadata(metadata)
    now = datetime.now(UTC)
    user_id, other_id, family = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(users.insert(), [{"id": user_id}, {"id": other_id}])

            def add_refresh(token, owner, *, active=False, family_id=None):
                connection.execute(
                    refresh.insert().values(
                        token=token,
                        user_id=owner,
                        family_id=family_id or uuid.uuid4(),
                        created_at=now,
                        expires_at=now + timedelta(days=1) if active else now,
                        revoked_at=None if active else now,
                    )
                )

            def add_access(token, owner, *, expired=True):
                connection.execute(
                    access.insert().values(
                        token=token,
                        user_id=owner,
                        created_at=now,
                        expires_at=now if expired else now + timedelta(days=1),
                        session_version=0,
                    )
                )

            for i in range(101):
                add_refresh(f"spent-{i}", user_id)
                add_access(f"expired-{i}", user_id)
            add_refresh("other-user", other_id)
            add_access("other-user", other_id)
            add_refresh("live-child", user_id, active=True, family_id=family)
            add_refresh("expired-ancestor", user_id, family_id=family)
            add_access("live-access", user_id, expired=False)

            class ExecuteAsync:
                async def execute(self, statement):
                    return connection.execute(statement)

            db = ExecuteAsync()
            asyncio.run(prune_tokens(db, user_id, now))
            for table, retained in (
                (refresh, {"other-user", "live-child", "expired-ancestor"}),
                (access, {"other-user", "live-access"}),
            ):
                tokens = set(connection.scalars(sa.select(table.c.token)))
                assert retained <= tokens
                assert len(tokens - retained) == 1  # only 100 spent rows per call
            asyncio.run(prune_tokens(db, user_id, now))
            assert set(connection.scalars(sa.select(refresh.c.token))) == {
                "other-user",
                "live-child",
                "expired-ancestor",
            }
            assert set(connection.scalars(sa.select(access.c.token))) == {
                "other-user",
                "live-access",
            }
    finally:
        engine.dispose()


def test_users_token_pair_persists_only_digests_with_sync_sqlite():
    from users.auth_local.token_api import _create_token_pair

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    users = sa.Table("users_user", metadata, sa.Column("id", GUID(), primary_key=True))
    refresh = RefreshToken.__table__.to_metadata(metadata)
    access = UserAccessToken.__table__.to_metadata(metadata)
    user_id = uuid.uuid4()
    try:
        metadata.create_all(engine)
        with Session(engine) as session:
            session.execute(users.insert().values(id=user_id))

            pair = asyncio.run(
                _create_token_pair(
                    _SyncSession(session),
                    user_id,
                    SimpleNamespace(
                        bearer_token_lifetime_seconds=900, refresh_token_lifetime_seconds=3600
                    ),
                )
            )
            for table, secret in ((access, pair.access_token), (refresh, pair.refresh_token)):
                stored = session.scalar(sa.select(table.c.token))
                assert stored == hashlib.sha256(secret.encode()).hexdigest()
    finally:
        engine.dispose()


class _SyncSession:
    """Run real SQL through async interfaces without the sandbox's aiosqlite hang."""

    def __init__(self, session):
        self.session = session

    def add(self, row):
        self.session.add(row)

    async def flush(self):
        self.session.flush()

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self):
        self.session.commit()

    async def refresh(self, row):
        self.session.refresh(row)

    async def delete(self, row):
        self.session.delete(row)


def test_users_cookie_strategy_hashes_prunes_and_destroys_with_sync_sqlite():
    from users.backend import build_strategy
    from users.db_adapter import PruningAccessTokenDatabase

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    users = sa.Table("users_user", metadata, sa.Column("id", GUID(), primary_key=True))
    RefreshToken.__table__.to_metadata(metadata)
    access = UserAccessToken.__table__.to_metadata(metadata)
    user_id = uuid.uuid4()
    try:
        metadata.create_all(engine)
        with Session(engine) as session:
            session.execute(users.insert().values(id=user_id))
            session.add(
                UserAccessToken(token="expired", user_id=user_id, expires_at=datetime.now(UTC))
            )
            session.commit()
            database = PruningAccessTokenDatabase(_SyncSession(session), UserAccessToken)
            strategy = build_strategy(database, 900)
            secret = asyncio.run(
                strategy.write_token(SimpleNamespace(id=user_id, session_version=2))
            )
            digest = hashlib.sha256(secret.encode()).hexdigest()
            assert list(session.scalars(sa.select(access.c.token))) == [digest]
            assert asyncio.run(database.get_by_token(secret)) is None
            assert asyncio.run(database.get_by_token(digest)).session_version == 2
            asyncio.run(strategy.destroy_token(digest, SimpleNamespace(id=user_id)))
            assert session.scalar(sa.select(sa.func.count()).select_from(access)) == 1
            asyncio.run(strategy.destroy_token(secret, SimpleNamespace(id=user_id)))
            assert session.scalar(sa.select(sa.func.count()).select_from(access)) == 0
    finally:
        engine.dispose()
