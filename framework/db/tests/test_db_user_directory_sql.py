"""Shared directory predicates treat SQL LIKE metacharacters as literal text."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from simple_module_db.user_directory_sql import (
    name_or_email_contains,
    search_rows,
    to_directory_user,
)
from sqlalchemy import Column, MetaData, String, Table, Uuid, literal, select
from sqlmodel import Session, create_engine


@pytest.mark.parametrize("term", ["%", "_", "\\"])
def test_name_or_email_contains_escapes_literal_metacharacters(term: str):
    with Session(create_engine("sqlite://")) as db:
        for full_name, email in [(f"Ada{term}Lovelace", "other"), (None, f"ada{term}@test")]:
            predicate = name_or_email_contains(literal(full_name), literal(email), term)
            assert db.exec(select(predicate)).scalar_one()
        predicate = name_or_email_contains(literal("Ada Lovelace"), literal("ada@test"), term)
        assert not db.exec(select(predicate)).scalar_one()


@pytest.mark.parametrize("roles", [None, (), ("editor",)])
def test_conversion_preserves_known_and_unknown_roles(roles: tuple[str, ...] | None):
    row = SimpleNamespace(email="ada@test", full_name=None)
    user = to_directory_user(row, "caller-id", roles=roles, is_active=False)
    assert user.id == "caller-id"
    assert user.email == row.email
    assert user.full_name is None
    assert user.roles == roles
    assert not user.is_active


async def test_chunk_merge_preserves_database_email_collation():
    identities = Table(
        "identities",
        MetaData(),
        Column("id", Uuid, primary_key=True),
        Column("email", String(collation="NOCASE")),
    )
    engine = create_engine("sqlite://")
    identities.create(engine)
    try:
        with Session(engine) as connection:
            ids = [UUID(int=n + 1) for n in range(501)]
            connection.execute(
                identities.insert(),
                [{"id": ids[n], "email": email} for n, email in [(0, "z"), (499, "B"), (500, "a")]],
            )
            db = SimpleNamespace(execute=AsyncMock(side_effect=connection.execute))
            rows = await search_rows(
                db,
                select(identities).order_by(identities.c.email),
                identities.c.id,
                include_ids=[str(uid) for uid in ids],
                limit=2,
            )
            assert [row.email for row in rows] == ["a", "B"]
    finally:
        engine.dispose()
