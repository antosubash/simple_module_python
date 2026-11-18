"""The cached provider honors the directory's filtered search contract too."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from keycloak.identity.directory import KeycloakDirectory
from keycloak.models import KeycloakUserCache
from sqlalchemy import create_engine


async def test_cache_search_filters_before_limit_and_matches_exact_email():
    engine = create_engine("sqlite://")
    KeycloakUserCache.__table__.create(engine)
    try:
        with engine.connect() as connection:
            ids = [uuid.uuid4() for _ in range(202)]
            for n, uid in enumerate(ids):
                connection.execute(
                    KeycloakUserCache.__table__.insert().values(
                        id=uid,
                        keycloak_sub=f"sub-{n}",
                        email=f"alex{n:03}@example.com",
                    )
                )
            db = SimpleNamespace(execute=AsyncMock(side_effect=connection.execute))
            directory = KeycloakDirectory()
            allowed = [str(uid) for uid in ids[-2:]]
            found = await directory.search(
                db,
                "alex",
                limit=1,
                include_ids=allowed,
                exclude_ids=[allowed[0]],
                active_only=True,
            )
            assert [u.id for u in found] == [allowed[1]]
            assert await directory.search(db, "alex", limit=1, include_ids=[]) == []
            found = await directory.search(db, "ALEX201@EXAMPLE.COM", limit=1, exact_email=True)
            assert [u.id for u in found] == [allowed[1]]
            assert await directory.search(db, "alex", limit=1, exact_email=True) == []
    finally:
        engine.dispose()
