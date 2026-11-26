"""The cached provider honors the directory's filtered search contract too."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from keycloak.identity.directory import KeycloakDirectory
from keycloak.models import KeycloakUserCache
from oidc.identity.directory import OidcDirectory
from sqlalchemy import create_engine


@pytest.fixture(params=[KeycloakDirectory, OidcDirectory])
def cache_directory_db(request):
    directory = request.param()
    engine = create_engine("sqlite://")
    directory.model.__table__.create(engine)
    try:
        with engine.connect() as connection:
            yield (
                directory,
                SimpleNamespace(execute=AsyncMock(side_effect=connection.execute)),
                connection,
            )
    finally:
        engine.dispose()


def insert_cached_user(directory, connection, email, **kwargs):
    uid = uuid.uuid4()
    identity = (
        {"keycloak_sub": str(uid)}
        if directory.model is KeycloakUserCache
        else {"issuer": "https://idp", "subject": str(uid)}
    )
    connection.execute(
        directory.model.__table__.insert().values(id=uid, email=email, **identity, **kwargs)
    )
    return str(uid)


async def test_name_only_cache_search_filters_before_limit(cache_directory_db):
    directory, db, connection = cache_directory_db
    email_match = insert_cached_user(directory, connection, "alex@example.com")
    insert_cached_user(directory, connection, "empty@example.com", full_name="")
    named = insert_cached_user(directory, connection, "z@example.com", full_name="Alex Smith")
    assert [u.id for u in await directory.search(db, "alex", limit=1)] == [email_match]
    found = await directory.search(db, " ALEX ", limit=1, match_email=False)
    assert [u.id for u in found] == [named]
    assert await directory.search(db, "alex", limit=1, match_email=False, include_ids=[]) == []
    assert await directory.search(db, "alex", limit=1, match_email=False, exclude_ids=[named]) == []
    assert len(await directory.search(db, " ", limit=10, match_email=False)) == 3


@pytest.mark.parametrize("term", ["%", "_", "\\"])
async def test_name_only_cache_search_matches_literal_metacharacters(cache_directory_db, term):
    directory, db, connection = cache_directory_db
    insert_cached_user(directory, connection, f"a{term}@example.com", full_name="Ada")
    named = insert_cached_user(directory, connection, "z@example.com", full_name=f"Ada{term}")
    found = await directory.search(db, term, limit=1, match_email=False)
    assert [u.id for u in found] == [named]


async def test_cache_find_by_email_is_exact_case_insensitive_and_literal(cache_directory_db):
    directory, db, connection = cache_directory_db
    named = insert_cached_user(directory, connection, "Ada_X@Example.com", full_name="Ada")
    insert_cached_user(directory, connection, "adaYx@example.com", full_name="Ada_X@Example.com")
    insert_cached_user(directory, connection, "", full_name="Unknown email")
    found = await directory.find_by_email(db, " ADA_X@EXAMPLE.COM ")
    assert found is not None and found.id == named
    assert found.full_name == "Ada"
    for email in ["ada", "%@example.com", "missing@example.com", "", " "]:
        assert await directory.find_by_email(db, email) is None
    found = await directory.search(
        db, "ada_x@example.com", limit=1, match_email=False, exact_email=True
    )
    assert [u.id for u in found] == [named]


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
