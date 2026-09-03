"""Entity cells name the row that changed, not the table it lives in.

An audit row stores a class name and a primary key. Rendering "User a91f3c2b…"
tells a reader which *kind* of thing changed and nothing about *which* one, so
every investigation starts by pasting the id into another screen. The owning
module is the only code that knows a ``Setting`` is named by its key and a
``User`` by ``full_name or email``, so it supplies a batch resolver alongside
its link, and the browse view spends it once per entity type per page.
"""

from __future__ import annotations

import uuid

import httpx
from _entity_label_support import browse as _browse
from _entity_label_support import entity_of as _entity
from _entity_label_support import seed_entry as _seed_entry
from background_tasks.models import TaskExecution
from feature_flags.models import FeatureFlagOverride
from settings.models import Setting
from users.models import User


class TestUserLabels:
    async def test_a_user_row_is_named_by_full_name(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            user = User(
                email="sam@example.com",
                hashed_password="x",
                full_name="Sam Okafor",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            user_id = str(user.id)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        entity = _entity(await _browse(authenticated_client), user_id)

        assert entity["display"] == "Sam Okafor"
        assert entity["table_name"] == "users_user"

    async def test_a_nameless_user_falls_back_to_the_email(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The deck's fourth row is "rob@example.com" — an invite that has not
        been accepted has no name yet, and the email is what identifies it."""
        async with app.state.sm.db.session_factory() as session:
            user = User(email="rob@example.com", hashed_password="x", is_active=True)
            session.add(user)
            await session.commit()
            user_id = str(user.id)
        await _seed_entry(app, entity_type="User", entity_id=user_id)

        assert _entity(await _browse(authenticated_client), user_id)["display"] == "rob@example.com"

    async def test_a_deleted_row_falls_back_to_the_id(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The record outlives the row it describes; the id is still the truth."""
        gone = str(uuid.uuid4())
        await _seed_entry(app, entity_type="User", entity_id=gone)

        assert _entity(await _browse(authenticated_client), gone)["display"] == gone


class TestOtherModuleLabels:
    async def test_a_setting_is_named_by_its_key(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            row = Setting(key="users.smtp_host", value="mail.example.com")
            session.add(row)
            await session.commit()
            row_id = str(row.id)
        await _seed_entry(app, entity_type="Setting", entity_id=row_id)

        entity = _entity(await _browse(authenticated_client), row_id)

        assert entity["display"] == "users.smtp_host"
        assert entity["table_name"] == "settings_setting"

    async def test_a_task_execution_is_named_by_its_task(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        async with app.state.sm.db.session_factory() as session:
            row = TaskExecution(
                celery_task_id=str(uuid.uuid4()), task_name="files.generate_thumbnail"
            )
            session.add(row)
            await session.commit()
            row_id = str(row.id)
        await _seed_entry(app, entity_type="TaskExecution", entity_id=row_id)

        entity = _entity(await _browse(authenticated_client), row_id)

        assert entity["display"] == "files.generate_thumbnail"
        assert entity["table_name"] == "background_tasks_task_execution"

    async def test_a_flag_override_is_named_by_the_flag_not_the_row_id(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """An override's primary key is a meaningless integer. What the reader
        is looking for is which flag was toggled."""
        async with app.state.sm.db.session_factory() as session:
            row = FeatureFlagOverride(name="beta_dashboard", enabled=True)
            session.add(row)
            await session.commit()
            row_id = str(row.id)
        await _seed_entry(app, entity_type="FeatureFlagOverride", entity_id=row_id)

        entity = _entity(await _browse(authenticated_client), row_id)

        assert entity["display"] == "beta_dashboard"
        assert entity["table_name"] == "feature_flags_override"

    async def test_an_unclaimed_type_shows_a_table_name_and_the_id(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """Join rows have no owner and no screen — the tag still says something,
        in the same snake_case vocabulary as every claimed row's tag."""
        await _seed_entry(app, entity_type="UserRole", entity_id="7")

        entity = _entity(await _browse(authenticated_client), "7")

        assert entity["display"] == "7"
        assert entity["table_name"] == "user_role"
        assert entity["url"] is None

    async def test_a_stored_file_is_named_by_its_filename(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """ "q3-report.pdf", not "StoredFile" and a uuid.

        There is no page for a file, so the link stays null — but the module
        that owns the table is still the only thing that can name the row.
        """
        from file_storage.models import StoredFile

        async with app.state.sm.db.session_factory() as session:
            stored = StoredFile(
                key="k/q3-report.pdf",
                filename="q3-report.pdf",
                content_type="application/pdf",
                size_bytes=12,
                backend="filesystem",
                checksum_sha256="0" * 64,
            )
            session.add(stored)
            await session.commit()
            file_id = str(stored.id)

        await _seed_entry(app, entity_type="StoredFile", entity_id=file_id)

        entity = _entity(await _browse(authenticated_client), file_id)

        assert entity["display"] == "q3-report.pdf"
        assert entity["table_name"] == "file_storage_stored_file"
        assert entity["url"] is None

    async def test_a_role_grant_reads_as_role_and_permission(
        self, app, authenticated_client: httpx.AsyncClient
    ) -> None:
        """The composite key was rendering as a Python tuple repr."""
        entity_id = "('admin', 'settings.create')"
        await _seed_entry(app, entity_type="RolePermission", entity_id=entity_id)

        entity = _entity(await _browse(authenticated_client), entity_id)

        assert entity["display"] == "admin · settings.create"
        assert entity["table_name"] == "permissions_role_permission"
