"""The edit page's "Recent activity" card, and its absence.

The card reads the audit log, which is an optional module. Two states have to
stay distinguishable: a deployment that records nothing (prop is ``None``, no
card) and an account that has done nothing yet (prop is ``[]``, empty card).
Collapsing them hides the difference between "we don't keep this" and "there
is nothing to keep".

The first version of this compared the registered module name against the menu
label ``"Audit log"`` rather than the registered ``"AuditLog"``, so the prop was
always ``None`` and the card never rendered anywhere. Hence a test that asserts
on a real entry rather than only on the absent case.
"""

from __future__ import annotations

import uuid

import pytest

_INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


async def _admin_id(users_app) -> uuid.UUID:
    from sqlalchemy import select
    from users.models import User

    async with users_app.state.sm.db.session_factory() as session:
        return (
            await session.execute(select(User.id).where(User.email == "admin@example.com"))
        ).scalar_one()


async def _edit_props(client, user_id) -> dict:
    resp = await client.get(f"/admin/users/{user_id}", headers=_INERTIA)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


class TestRecentActivity:
    @pytest.mark.anyio
    async def test_prop_is_a_list_when_audit_log_is_installed(self, admin_client, users_app):
        """An installed audit log means a card, even before anything is recorded."""
        user_id = await _admin_id(users_app)
        props = await _edit_props(admin_client, user_id)
        assert isinstance(props["recent_activity"], list)

    @pytest.mark.anyio
    async def test_an_entry_by_this_actor_is_summarised(self, admin_client, users_app):
        from audit_log.models import AuditEntry

        user_id = await _admin_id(users_app)
        async with users_app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type="User",
                    entity_id=str(user_id),
                    action="update",
                    changes=[{"field": "is_active", "old": True, "new": False}],
                    user_id=str(user_id),
                )
            )
            await session.commit()

        rows = (await _edit_props(admin_client, user_id))["recent_activity"]
        assert len(rows) == 1
        row = rows[0]
        assert "is_active" in row["summary"]
        # The entity resolves to a person, not a raw uuid.
        assert "admin@example.com" in row["summary"] or "Test Admin" in row["summary"]
        assert row["href"].startswith("/admin/audit-log/?entity_type=User")
        assert row["at"]

    @pytest.mark.anyio
    async def test_only_this_actors_entries_appear(self, admin_client, users_app, users_db):
        from audit_log.models import AuditEntry
        from test_api_admin import _make_user

        user_id = await _admin_id(users_app)
        other = await _make_user(users_db, email="someone-else@example.com")
        async with users_app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type="User",
                    entity_id=str(user_id),
                    action="update",
                    changes=[{"field": "full_name"}],
                    user_id=str(other.id),
                )
            )
            await session.commit()

        assert (await _edit_props(admin_client, user_id))["recent_activity"] == []

    @pytest.mark.anyio
    async def test_a_non_user_entity_is_named_by_its_owning_module(
        self, admin_client, users_app
    ):
        """"Created setting users.smtp_host", not "Created setting 3f2a…".

        Before this the card reached only the users table, so every other kind
        of row came out as the model class lowercased plus a raw uuid — which
        names a Python class at a reader who is looking at a screen of
        settings.
        """
        from audit_log.models import AuditEntry
        from settings.models import Setting

        user_id = await _admin_id(users_app)
        async with users_app.state.sm.db.session_factory() as session:
            setting = Setting(key="users.smtp_host", value="mail.example.com")
            session.add(setting)
            await session.flush()
            session.add(
                AuditEntry(
                    entity_type=Setting.__name__,
                    entity_id=str(setting.id),
                    action="create",
                    changes=[],
                    user_id=str(user_id),
                )
            )
            await session.commit()

        rows = (await _edit_props(admin_client, user_id))["recent_activity"]
        assert [r["summary"] for r in rows] == ["Created setting users.smtp_host"]

    @pytest.mark.anyio
    async def test_a_row_nothing_can_name_falls_back_to_a_short_id(
        self, admin_client, users_app
    ):
        """No resolver for this type — the kind still reads, the id is trimmed."""
        from audit_log.models import AuditEntry

        user_id = await _admin_id(users_app)
        entity_id = "6b03e1a2-0000-4000-8000-000000000001"
        async with users_app.state.sm.db.session_factory() as session:
            session.add(
                AuditEntry(
                    entity_type="Unclaimed",
                    entity_id=entity_id,
                    action="create",
                    changes=[],
                    user_id=str(user_id),
                )
            )
            await session.commit()

        rows = (await _edit_props(admin_client, user_id))["recent_activity"]
        assert [r["summary"] for r in rows] == ["Created unclaimed 6b03e1a2"]

    @pytest.mark.anyio
    async def test_prop_is_none_when_audit_log_is_not_installed(self, admin_client, users_app):
        """Absent module, absent card — not an empty one claiming no activity."""
        sm = users_app.state.sm
        loaded = sm.modules
        trimmed = type(loaded)(m for m in loaded if getattr(m.meta, "name", "") != "AuditLog")
        assert len(trimmed) < len(loaded), "audit_log was not loaded, so this proves nothing"
        # ``sm`` is a frozen dataclass, so this is the only way to model an app
        # built without the module short of building a second one.
        object.__setattr__(sm, "modules", trimmed)
        try:
            user_id = await _admin_id(users_app)
            props = await _edit_props(admin_client, user_id)
            assert props["recent_activity"] is None
        finally:
            object.__setattr__(sm, "modules", loaded)
