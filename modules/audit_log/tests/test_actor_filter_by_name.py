"""The Actor filter takes a name, not a uuid.

The deck labels the field "Actor" and placeholders it "Anyone". Nobody
investigating an incident holds their colleague's primary key — they hold a
name or an email — and the previous field ("User ID", exact match on
``user_id``) could only be filled by copying an id back out of a row that had
already been found. Names are resolved to ids in the view; a uuid still means
exactly that uuid, because an id is unambiguous and a name never is.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
from audit_log.constants import ACTION_UPDATED
from audit_log.models import AuditEntry
from users.models import User

VIEW_URL = "/admin/audit-log/"
INERTIA_HEADERS = {"X-Inertia": "true", "Accept": "application/json"}
_ENTITY_TYPE = "Widget"


async def _seed(app) -> dict[str, str]:
    """Two accounts with an audit row each, plus one row by nobody."""
    ids: dict[str, str] = {}
    async with app.state.sm.db.session_factory() as session:
        for key, email, name in (
            ("sam", "sam@example.com", "Sam Okafor"),
            ("dana", "dana@other.test", "Dana Rivera"),
        ):
            user = User(email=email, hashed_password="x", full_name=name, is_active=True)
            session.add(user)
            await session.flush()
            ids[key] = str(user.id)
        await session.commit()

    async with app.state.sm.db.session_factory() as session:
        for key in ("sam", "dana"):
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id=key,
                    action=ACTION_UPDATED,
                    changes=[],
                    user_id=ids[key],
                )
            )
        session.add(
            AuditEntry(
                entity_type=_ENTITY_TYPE, entity_id="system", action=ACTION_UPDATED, changes=[]
            )
        )
        await session.commit()
    return ids


async def _entity_ids(client: httpx.AsyncClient, **params: str) -> list[str]:
    resp = await client.get(
        VIEW_URL, params={"entity_type": _ENTITY_TYPE, **params}, headers=INERTIA_HEADERS
    )
    assert resp.status_code == 200, resp.text
    return sorted(item["entity_id"] for item in resp.json()["props"]["items"])


class TestActorFilter:
    async def test_no_actor_filter_returns_every_row(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)

        assert await _entity_ids(authenticated_client) == ["dana", "sam", "system"]

    async def test_a_uuid_matches_that_actor_exactly(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        ids = await _seed(app)

        assert await _entity_ids(authenticated_client, user_id=ids["sam"]) == ["sam"]

    async def test_a_partial_name_matches_case_insensitively(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)

        assert await _entity_ids(authenticated_client, user_id="okafor") == ["sam"]

    async def test_an_email_fragment_matches(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)

        assert await _entity_ids(authenticated_client, user_id="dana@other") == ["dana"]

    async def test_a_name_matching_nobody_returns_nothing(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The dangerous failure is an unmatched name silently dropping the
        filter — an empty result reads as "no such activity" when it means
        "no such person"."""
        await _seed(app)

        assert await _entity_ids(authenticated_client, user_id="nobody at all") == []

    async def test_an_unknown_uuid_returns_nothing(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)

        assert await _entity_ids(authenticated_client, user_id=str(uuid.uuid4())) == []

    async def test_the_raw_term_is_echoed_back_to_the_field(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The input must keep showing what was typed, not the ids it resolved to."""
        await _seed(app)

        resp = await authenticated_client.get(
            VIEW_URL, params={"user_id": "okafor"}, headers=INERTIA_HEADERS
        )

        assert resp.json()["props"]["filters"]["user_id"] == "okafor"


class TestDateRange:
    """The picker is date-only, so ``to_date`` names a whole day. Treating it
    as midnight silently excludes everything that happened on the day the
    reader just chose as the end of the range."""

    async def test_to_date_includes_the_whole_day(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        stamp = datetime(2026, 8, 19, 14, 2, 11, tzinfo=UTC)
        async with app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id="afternoon",
                    action=ACTION_UPDATED,
                    changes=[],
                    created_at=stamp,
                )
            )
            await session.commit()

        found = await _entity_ids(
            authenticated_client, from_date="2026-08-01", to_date="2026-08-19"
        )

        assert found == ["afternoon"]


class TestActorSearchSafety:
    async def test_like_metacharacters_match_as_text(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """An unescaped ``%`` widens the search instead of narrowing it, which
        on this screen means showing activity by people the reader did not ask
        about."""
        await _seed(app)

        assert await _entity_ids(authenticated_client, user_id="%") == []

    async def test_underscore_is_not_a_single_character_wildcard(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed(app)

        assert await _entity_ids(authenticated_client, user_id="Sa_") == []
