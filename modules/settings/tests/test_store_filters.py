"""The raw override table filters, searches and pages on the server.

The screen used to receive every row in the database as one unpaginated prop.
That is fine with a dozen overrides and quietly unusable with a few thousand:
the payload, the render and the browser's find-in-page all scale with the whole
table rather than with what the admin asked for. The scope tabs also have to
report counts the client cannot compute once it only holds one page.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}
_STORE = "/admin/settings/store"


async def _seed(app: FastAPI) -> None:
    """25 system, 3 tenant and 2 user rows — enough to need a second page."""
    from settings.models import Setting

    async with app.state.sm.db.session_factory() as session:
        for i in range(25):
            session.add(Setting(scope="system", scope_id="", key=f"demo.system_{i:02d}", value="x"))
        for i in range(3):
            session.add(
                Setting(scope="tenant", scope_id="acme-co", key=f"demo.smtp_{i}", value="x")
            )
        for i in range(2):
            session.add(
                Setting(scope="user", scope_id="dana@example.com", key=f"demo.user_{i}", value="x")
            )
        await session.commit()


@pytest.fixture
async def seeded(app: FastAPI) -> FastAPI:
    await _seed(app)
    return app


async def _props(client: httpx.AsyncClient, query: str = "") -> dict:
    resp = await client.get(f"{_STORE}{query}", headers=_INERTIA)
    assert resp.status_code == 200, resp.text[:400]
    return resp.json()["props"]


class TestPaging:
    async def test_first_page_holds_twenty_rows_of_thirty(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = await _props(authenticated_client)

        assert len(props["settings"]) == 20
        assert props["pagination"] == {"page": 1, "per_page": 20, "total": 30}

    async def test_second_page_holds_the_remainder(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = await _props(authenticated_client, "?page=2")

        assert len(props["settings"]) == 10
        assert props["pagination"]["page"] == 2

    async def test_a_page_past_the_end_clamps_to_the_last_real_page(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """A stale ?page= link must show rows, not an empty table over "of 30"."""
        props = await _props(authenticated_client, "?page=99")

        assert props["pagination"]["page"] == 2
        assert len(props["settings"]) == 10

    async def test_page_zero_is_clamped_rather_than_echoed(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = await _props(authenticated_client, "?page=0")

        assert props["pagination"]["page"] == 1
        assert len(props["settings"]) == 20

    async def test_a_non_numeric_page_renders_the_first_page(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Same tolerance ``scope`` gets: a broken link still shows the table."""
        props = await _props(authenticated_client, "?page=abc&per_page=lots")

        assert props["pagination"] == {"page": 1, "per_page": 20, "total": 30}


class TestScopeFilter:
    async def test_scope_narrows_the_rows(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = await _props(authenticated_client, "?scope=tenant")

        assert len(props["settings"]) == 3
        assert {row["scope"] for row in props["settings"]} == {"tenant"}
        assert props["pagination"]["total"] == 3
        assert props["filters"]["scope"] == "tenant"

    async def test_all_is_the_default_and_keeps_every_scope(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = await _props(authenticated_client)

        assert props["filters"] == {"scope": "all", "q": ""}
        assert props["pagination"]["total"] == 30

    async def test_an_unknown_scope_falls_back_to_all(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """A hand-edited ?scope= must not 500 or silently show zero rows."""
        props = await _props(authenticated_client, "?scope=nonsense")

        assert props["filters"]["scope"] == "all"
        assert props["pagination"]["total"] == 30


class TestSearch:
    async def test_q_matches_keys_case_insensitively(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = await _props(authenticated_client, "?q=SMTP")

        assert props["pagination"]["total"] == 3
        assert all("smtp" in row["key"] for row in props["settings"])
        assert props["filters"]["q"] == "SMTP"

    async def test_like_wildcards_in_the_query_are_literal(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Keys are full of underscores, and `_`/`%` are LIKE wildcards."""
        assert (await _props(authenticated_client, "?q=demo.s%25"))["pagination"]["total"] == 0
        assert (await _props(authenticated_client, "?q=demo.s_stem"))["pagination"]["total"] == 0

    async def test_q_combines_with_scope(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = await _props(authenticated_client, "?q=smtp&scope=system")

        assert props["pagination"]["total"] == 0
        assert props["settings"] == []


class TestCounts:
    async def test_counts_cover_every_tab(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        props = await _props(authenticated_client)

        assert props["counts"] == {"all": 30, "system": 25, "tenant": 3, "user": 2}

    async def test_counts_ignore_the_selected_scope(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Otherwise every unselected tab reads 0 and the tabs stop being usable."""
        props = await _props(authenticated_client, "?scope=user")

        assert props["counts"] == {"all": 30, "system": 25, "tenant": 3, "user": 2}

    async def test_counts_do_follow_the_search(
        self, seeded: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The tabs describe the current result set, so "system 0" is the answer."""
        props = await _props(authenticated_client, "?q=smtp")

        assert props["counts"] == {"all": 3, "system": 0, "tenant": 3, "user": 0}


class TestServiceQuery:
    """The service owns the query; the view only clamps and shapes it."""

    async def test_search_and_page_return_rows_and_the_unpaged_total(self, db_session) -> None:
        from settings.models import Setting
        from settings.service import SettingService

        for i in range(5):
            db_session.add(Setting(scope="system", scope_id="", key=f"a.key_{i}", value="v"))
        await db_session.flush()

        rows, total = await SettingService(db_session).list_filtered(
            scope=None, q="key_", page=2, per_page=2
        )

        assert total == 5
        assert [r.key for r in rows] == ["a.key_2", "a.key_3"]

    async def test_counts_by_scope_names_every_scope_even_at_zero(self, db_session) -> None:
        from settings.models import Setting
        from settings.service import SettingService

        db_session.add(Setting(scope="system", scope_id="", key="a.b", value="v"))
        await db_session.flush()

        counts = await SettingService(db_session).count_by_scope()

        assert counts == {"all": 1, "system": 1, "tenant": 0, "user": 0}
