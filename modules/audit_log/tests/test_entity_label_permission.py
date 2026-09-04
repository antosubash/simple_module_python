"""Naming an audited row is a read of that row, and takes that row's permission.

``audit_log.view`` says "may read the audit trail". It was also, accidentally,
saying "may read the display name and email of every account that appears in
it": the entity column asks each owning module to name its own rows, and the
users module names an account by ``full_name or email`` — falling through to the
raw email for any account still holding an unaccepted invite. A role granted
audit access and nothing else could page through the log and harvest the
directory that ``users.manage`` guards at the front door.

So an ``AuditLink`` may declare a ``label_permission``, and a reader without it
gets the id the row actually stored. The entry itself is never withheld — the
action, the type, the timestamp and the id are the audit trail, and an auditor
who cannot see them is not an auditor. GH #300.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from _entity_label_support import browse as _browse
from _entity_label_support import entity_of as _entity
from _entity_label_support import seed_entry as _seed_entry
from audit_log.constants import PERM_VIEW
from audit_log.resolve import resolve_entity_labels
from settings.models import Setting
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from simple_module_test import forge_session_cookie
from sqlalchemy.ext.asyncio import AsyncSession
from users.constants import PERM_USERS_MANAGE
from users.models import User

EXPORT_URL = "/api/audit_log/export.csv"
_AUDITOR_ROLE = "auditor"

_NAME = "Sam Okafor"
_EMAIL = "sam@example.com"


async def _seed_user(app, *, email: str = _EMAIL, full_name: str | None = _NAME) -> str:
    """A user account for the audit row to point at, returning its id."""
    async with app.state.sm.db.session_factory() as session:
        user = User(email=email, hashed_password="x", full_name=full_name, is_active=True)
        session.add(user)
        await session.commit()
        return str(user.id)


async def _reader(app, *, permissions: list[str], email: str) -> AsyncIterator[httpx.AsyncClient]:
    """A signed-in client whose single role holds exactly *permissions*.

    Built the long way (a real account, a real role, a forged session cookie)
    rather than by stubbing the permission set, because the thing under test is
    whether the view consults the *requesting principal's* grants at all — a
    stub would pass even if it consulted nothing.
    """
    from sqlalchemy import select
    from users.models import UserRole
    from users.models.role import Role

    async with app.state.sm.db.session_factory() as session:
        user = User(email=email, hashed_password="x", is_active=True, is_verified=True)
        session.add(user)
        await session.flush()
        # Get-or-create: the `app` fixture already seeded an admin, so the
        # 'admin' Role exists and Role.name is unique.
        role = (
            await session.execute(select(Role).where(Role.name == _AUDITOR_ROLE))
        ).scalar_one_or_none()
        if role is None:
            role = Role(name=_AUDITOR_ROLE)
            session.add(role)
            await session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
        user_id = str(user.id)
        await session.commit()

    app.state.sm.permissions.map_role(_AUDITOR_ROLE, permissions)

    cookie = forge_session_cookie(str(app.state.sm.settings.secret_key), {"user_id": user_id})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"session": cookie},
    ) as client:
        yield client


@pytest.fixture
async def auditor(app) -> AsyncIterator[httpx.AsyncClient]:
    """Holds ``audit_log.view`` and nothing else — the role in the report."""
    async for client in _reader(app, permissions=[PERM_VIEW], email="auditor@example.com"):
        yield client


@pytest.fixture
async def auditor_who_manages_users(app) -> AsyncIterator[httpx.AsyncClient]:
    """Holds both grants, so the names are theirs to see."""
    async for client in _reader(
        app,
        permissions=[PERM_VIEW, PERM_USERS_MANAGE],
        email="user-admin@example.com",
    ):
        yield client


class TestBrowseWithheldFromAuditOnlyReaders:
    async def test_the_name_is_replaced_by_the_id(self, app, auditor) -> None:
        user_id = await _seed_user(app)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        entity = _entity(await _browse(auditor), user_id)

        assert entity["display"] == user_id
        assert _NAME not in str(entity)

    async def test_an_outstanding_invite_does_not_leak_its_email(self, app, auditor) -> None:
        """The worst case: no ``full_name`` yet, so the label *is* the email.

        Scoped to the entity column on purpose. Creating the account also wrote
        its own ``created`` entry, whose ``changes`` blob records the email as
        the value that was set — that is the audit trail doing its job, and a
        separate surface from the one this file is about.
        """
        user_id = await _seed_user(app, email="rob@example.com", full_name=None)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        props = await _browse(auditor)

        assert _entity(props, user_id)["display"] == user_id
        assert "rob@example.com" not in [item["entity"]["display"] for item in props["items"]]

    async def test_the_audit_row_itself_is_still_readable(self, app, auditor) -> None:
        """Withholding the name must not withhold the record. An auditor who
        cannot see what happened is not an auditor."""
        user_id = await _seed_user(app)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        row = next(i for i in (await _browse(auditor))["items"] if i["entity_id"] == user_id)

        assert row["entity_type"] == "User"
        assert row["action"] == "updated"
        assert row["entity"]["table_name"] == "users_user"
        assert row["entity"]["url"] == f"/admin/users/{user_id}"

    async def test_an_ungated_type_is_still_named(self, app, auditor) -> None:
        """Only the types whose owner asked for a gate are affected — a setting
        key is what changed, not who somebody is."""
        async with app.state.sm.db.session_factory() as session:
            row = Setting(key="users.smtp_host", value="mail.example.com")
            session.add(row)
            await session.commit()
            row_id = str(row.id)
        await _seed_entry(app, entity_type="Setting", entity_id=row_id)

        assert _entity(await _browse(auditor), row_id)["display"] == "users.smtp_host"


class TestBrowseShownToPermittedReaders:
    async def test_users_manage_sees_the_name(self, app, auditor_who_manages_users) -> None:
        user_id = await _seed_user(app)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        entity = _entity(await _browse(auditor_who_manages_users), user_id)

        assert entity["display"] == _NAME

    async def test_the_admin_wildcard_still_sees_the_name(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """``admin`` holds ``*`` rather than a list, so the gate has to honour
        the wildcard or it locks out the one role that always could."""
        user_id = await _seed_user(app, email="wild@example.com", full_name="Wilder Name")
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        entity = _entity(await _browse(authenticated_client), user_id)

        assert entity["display"] == "Wilder Name"


class TestExportFollowsTheScreen:
    """The CSV is a second door onto the same rows; a guard on one is no guard."""

    async def _labels(self, client: httpx.AsyncClient, entity_id: str) -> set[str]:
        """Every distinct ``entity_label`` the export gives that row.

        A set because seeding the account wrote its own ``created`` entry
        alongside the one the test adds, and both name the same row — what
        matters is what they are *called*, not how many there are.
        """
        resp = await client.get(EXPORT_URL)
        assert resp.status_code == 200, resp.text
        return {
            row["entity_label"]
            for row in csv.DictReader(io.StringIO(resp.text))
            if row["entity_id"] == entity_id
        }

    async def test_the_name_is_not_downloadable_either(self, app, auditor) -> None:
        user_id = await _seed_user(app)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        assert await self._labels(auditor, user_id) == {user_id}

    async def test_a_permitted_reader_still_exports_the_name(
        self, app, auditor_who_manages_users
    ) -> None:
        user_id = await _seed_user(app)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        assert await self._labels(auditor_who_manages_users, user_id) == {_NAME}


class TestResolverGate:
    """The unit underneath, so a regression names the line rather than a page."""

    def _registry(self) -> AuditLinkRegistry:
        registry = AuditLinkRegistry()
        registry.register(
            AuditLink(
                entity_type="Secret",
                url_template="/s/{id}",
                label_resolver=self._never_called,
                label_permission="secrets.view",
            )
        )
        return registry

    async def _never_called(self, _db, ids: list[str]) -> dict[str, str]:
        return {i: f"name-{i}" for i in ids}

    async def test_a_reader_without_the_permission_gets_nothing(
        self, db_session: AsyncSession
    ) -> None:
        labels = await resolve_entity_labels(
            db_session, self._registry(), [("Secret", "a")], {"audit_log.view"}
        )

        assert labels == {}

    async def test_a_reader_with_it_gets_the_name(self, db_session: AsyncSession) -> None:
        labels = await resolve_entity_labels(
            db_session, self._registry(), [("Secret", "a")], {"secrets.view"}
        )

        assert labels == {("Secret", "a"): "name-a"}

    async def test_the_wildcard_satisfies_it(self, db_session: AsyncSession) -> None:
        labels = await resolve_entity_labels(db_session, self._registry(), [("Secret", "a")], {"*"})

        assert labels == {("Secret", "a"): "name-a"}

    async def test_the_resolver_is_not_even_run(self, db_session: AsyncSession) -> None:
        """Skipped before dispatch, not filtered after: a resolver that is not
        allowed to answer must not be allowed to query either."""
        calls: list[list[str]] = []

        async def resolve(_db, ids: list[str]) -> dict[str, str]:
            calls.append(ids)
            return {}

        registry = AuditLinkRegistry()
        registry.register(
            AuditLink(
                entity_type="Secret",
                url_template="/s/{id}",
                label_resolver=resolve,
                label_permission="secrets.view",
            )
        )

        await resolve_entity_labels(db_session, registry, [("Secret", str(uuid.uuid4()))], set())

        assert calls == []
