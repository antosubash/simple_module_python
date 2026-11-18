"""The cached provider honors the directory's filtered search contract too."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from keycloak.identity.directory import KeycloakDirectory
from keycloak.models import KeycloakUserCache
from oidc.identity.directory import OidcDirectory
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


@pytest.mark.parametrize("directory", [KeycloakDirectory(), OidcDirectory()])
async def test_large_cache_member_filter_chunks_queries_and_keeps_global_limit(directory):
    engine = create_engine("sqlite://")
    model = directory.model
    model.__table__.create(engine)
    ids = [uuid.UUID(int=n + 1) for n in range(32768)]
    try:
        with engine.connect() as connection:
            for index, email in [(0, "z@test"), (500, "b@test"), (1000, "c@test"), (-1, "a@test")]:
                identity = (
                    {"keycloak_sub": str(index)}
                    if model is KeycloakUserCache
                    else {"issuer": "https://idp", "subject": str(index)}
                )
                connection.execute(
                    model.__table__.insert().values(id=ids[index], email=email, **identity)
                )
            db = SimpleNamespace(execute=AsyncMock(side_effect=connection.execute))
            found = await directory.search(db, None, limit=3, include_ids=[str(uid) for uid in ids])
            assert [user.email for user in found] == ["a@test", "b@test", "c@test"]
            statements = [call.args[0] for call in db.execute.call_args_list]
            assert len(statements) > 1
            assert all(
                len(stmt.compile(compile_kwargs={"render_postcompile": True}).params) <= 505
                for stmt in statements
            )
    finally:
        engine.dispose()
