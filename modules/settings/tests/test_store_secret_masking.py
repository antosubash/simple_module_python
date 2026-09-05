"""The raw key/value store hides credentials on the same rule as the editor.

``SettingService._out`` masked only exact matches against ``SENSITIVE_KEYS``,
a single-entry frozenset holding ``host.secret_key``. The store screen shows
the *same data* as the module editor through a different lens, so an override
named ``users.smtp_password`` — or any override holding a DSN with a password
in its authority — rendered in clear text in the browse table and pre-filled
into the edit form, for anyone holding ``settings.view``.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from settings._row_masking import is_masked
from settings.constants import SENSITIVE_PLACEHOLDER, VALUE_TYPE_INT, VALUE_TYPE_STRING
from settings.contracts.schemas import SettingCreate, SettingScope
from settings.models import Setting
from settings.service import SettingService

_DSN = "postgresql://svc:hunter2@db.internal/app"


def _row(key: str, value: str, value_type: str = VALUE_TYPE_STRING) -> Setting:
    return Setting(
        scope=SettingScope.SYSTEM.value, scope_id="", key=key, value=value, value_type=value_type
    )


class TestWhatCountsAsMasked:
    @pytest.mark.parametrize(
        "key,value",
        [
            ("host.secret_key", "s3kr3t"),
            ("users.smtp_password", "hunter2"),
            ("users.mailer_api_key", "sk-live-abc"),
            ("background_tasks.broker_url", _DSN),
        ],
    )
    def test_credentials_are_masked(self, key: str, value: str) -> None:
        assert is_masked(_row(key, value)) is True

    @pytest.mark.parametrize(
        "key,value,value_type",
        [
            # A DSN with no password in it is not a credential — hiding
            # `redis://localhost:6379/0` helps nobody debug an idle queue.
            ("background_tasks.broker_url", "redis://localhost:6379/0", VALUE_TYPE_STRING),
            ("users.smtp_host", "smtp.example.com", VALUE_TYPE_STRING),
            # A numeric field matching "password" by name only. Masking this
            # made a lifetime uneditable in the module editor; the store must
            # not reintroduce that.
            ("users.reset_password_token_lifetime_seconds", "3600", VALUE_TYPE_INT),
        ],
    )
    def test_ordinary_values_stay_visible(self, key: str, value: str, value_type: str) -> None:
        assert is_masked(_row(key, value, value_type)) is False


class TestReadPathsMask:
    async def test_browse_table_masks_a_password_override(self, db_session) -> None:
        service = SettingService(db_session)
        await service.create(
            SettingCreate(
                scope=SettingScope.SYSTEM,
                scope_id="",
                key="users.smtp_password",
                value="hunter2",
                value_type=VALUE_TYPE_STRING,
            )
        )
        items, _ = await service.list_filtered()
        assert [i.value for i in items] == [SENSITIVE_PLACEHOLDER]

    async def test_get_by_id_masks_a_dsn_override(self, db_session) -> None:
        service = SettingService(db_session)
        created = await service.create(
            SettingCreate(
                scope=SettingScope.SYSTEM,
                scope_id="",
                key="background_tasks.broker_url",
                value=_DSN,
                value_type=VALUE_TYPE_STRING,
            )
        )
        assert created.value == SENSITIVE_PLACEHOLDER
        fetched = await service.get_by_id(created.id)
        assert fetched is not None
        assert fetched.value == SENSITIVE_PLACEHOLDER

    async def test_the_store_screen_masks_it_too(
        self, app: FastAPI, authenticated_client: httpx.AsyncClient
    ) -> None:
        """End to end: the browse table an admin actually reads."""
        async with app.state.sm.db.session_factory() as session:
            session.add(_row("users.smtp_password", "hunter2"))
            session.add(_row("background_tasks.broker_url", _DSN))
            session.add(_row("users.smtp_host", "smtp.example.com"))
            await session.commit()

        resp = await authenticated_client.get(
            "/admin/settings/store", headers={"X-Inertia": "true", "X-Inertia-Version": "1.0"}
        )
        assert resp.status_code == 200
        rows = {r["key"]: r["value"] for r in resp.json()["props"]["settings"]}

        assert rows["users.smtp_password"] == SENSITIVE_PLACEHOLDER
        assert rows["background_tasks.broker_url"] == SENSITIVE_PLACEHOLDER
        assert rows["users.smtp_host"] == "smtp.example.com"


class TestSavingAnUntouchedForm:
    async def test_echoing_the_mask_leaves_the_real_value_alone(self, db_session) -> None:
        """The edit form pre-fills from the masked read. An admin who opens a
        credential row and clicks Save without touching the field must not
        overwrite it with the placeholder."""
        from settings.contracts.schemas import SettingUpdate

        service = SettingService(db_session)
        created = await service.create(
            SettingCreate(
                scope=SettingScope.SYSTEM,
                scope_id="",
                key="users.smtp_password",
                value="hunter2",
                value_type=VALUE_TYPE_STRING,
            )
        )
        await service.update(
            created.id, SettingUpdate(value=SENSITIVE_PLACEHOLDER, description="note")
        )

        stored = await db_session.get(Setting, created.id)
        assert stored.value == "hunter2"
        assert stored.description == "note"

    async def test_a_real_new_credential_still_saves(self, db_session) -> None:
        from settings.contracts.schemas import SettingUpdate

        service = SettingService(db_session)
        created = await service.create(
            SettingCreate(
                scope=SettingScope.SYSTEM,
                scope_id="",
                key="users.smtp_password",
                value="hunter2",
                value_type=VALUE_TYPE_STRING,
            )
        )
        await service.update(created.id, SettingUpdate(value="correct-horse"))

        stored = await db_session.get(Setting, created.id)
        assert stored.value == "correct-horse"

    async def test_the_placeholder_is_stored_on_a_row_that_is_not_masked(self, db_session) -> None:
        """Nothing was hidden on this row, so the write is a real edit rather
        than an echo — dropping it would discard it with nothing to show."""
        from settings.contracts.schemas import SettingUpdate

        service = SettingService(db_session)
        created = await service.create(
            SettingCreate(
                scope=SettingScope.SYSTEM,
                scope_id="",
                key="ui.divider",
                value="—",
                value_type=VALUE_TYPE_STRING,
            )
        )
        await service.update(created.id, SettingUpdate(value=SENSITIVE_PLACEHOLDER))

        stored = await db_session.get(Setting, created.id)
        assert stored.value == SENSITIVE_PLACEHOLDER


class TestTheMaskStopsAtTheScreen:
    """Masking is for the screens. The code that *applies* a setting has to see
    the real value, or hydration writes a row of dots over every credential the
    deployment stored — a mailer that cannot authenticate, and a
    ``reset_password_token_secret`` that no longer verifies the tokens it signed.
    """

    async def test_the_store_reads_through_the_mask(self, db_session) -> None:
        from settings.constants import SYSTEM_SCOPE_ID
        from settings.store import SettingsStore

        service = SettingService(db_session)
        await service.create(
            SettingCreate(
                scope=SettingScope.SYSTEM,
                scope_id=SYSTEM_SCOPE_ID,
                key="users.reset_password_token_secret",
                value="s3kr3t",
                value_type=VALUE_TYPE_STRING,
            )
        )
        overrides = await SettingsStore(service).get_overrides("users")

        assert overrides["reset_password_token_secret"] == ("s3kr3t", VALUE_TYPE_STRING)

    async def test_a_consumer_module_reads_the_real_value(self, db_session) -> None:
        """``SettingsAccessor.get`` is what another module calls to obtain a
        value it is about to use, not to render."""
        service = SettingService(db_session)
        await service.create(
            SettingCreate(
                scope=SettingScope.SYSTEM,
                scope_id="",
                key="orders.stripe_api_key",
                value="sk-live-abc",
                value_type=VALUE_TYPE_STRING,
            )
        )
        assert await service.get_resolved_value("orders.stripe_api_key") == "sk-live-abc"

    async def test_the_resolve_endpoint_still_masks_the_same_row(self, db_session) -> None:
        """The two readings of one row: the API renders, the consumer acts."""
        service = SettingService(db_session)
        await service.create(
            SettingCreate(
                scope=SettingScope.SYSTEM,
                scope_id="",
                key="orders.stripe_api_key",
                value="sk-live-abc",
                value_type=VALUE_TYPE_STRING,
            )
        )
        resolved = await service.resolve("orders.stripe_api_key")
        assert resolved is not None
        assert resolved.value == SENSITIVE_PLACEHOLDER
