"""The session-signing key must not be readable back through the settings API.

Making ``SM_SECRET_KEY`` optional means the hosting layer generates one and
stores it as ``host.secret_key``. That put it in the same key/value table the
settings API lists and the admin browse screen renders — and anyone who can
read it can forge a session cookie for any account.

The masking has to hold on *every* read path, and must not break the boot-time
reader, which resolves the real value through raw SQL rather than this service.
"""

from __future__ import annotations

import pytest
from settings.constants import SENSITIVE_PLACEHOLDER, SYSTEM_SCOPE_ID
from settings.contracts.schemas import SettingCreate, SettingScope
from settings.service import SettingService

pytestmark = pytest.mark.anyio

_REAL = "a-real-session-signing-key-value"


async def _seed_secret(db_session) -> int:
    service = SettingService(db_session)
    created = await service.create(
        SettingCreate(
            scope=SettingScope.SYSTEM,
            scope_id=SYSTEM_SCOPE_ID,
            key="host.secret_key",
            value=_REAL,
            value_type="string",
        )
    )
    await db_session.commit()
    return created.id


async def test_create_does_not_echo_the_secret(db_session) -> None:
    service = SettingService(db_session)
    created = await service.create(
        SettingCreate(
            scope=SettingScope.SYSTEM,
            scope_id=SYSTEM_SCOPE_ID,
            key="host.secret_key",
            value=_REAL,
            value_type="string",
        )
    )

    assert created.value == SENSITIVE_PLACEHOLDER


async def test_every_read_path_masks(db_session) -> None:
    setting_id = await _seed_secret(db_session)
    service = SettingService(db_session)

    by_id = await service.get_by_id(setting_id)
    scoped = await service.get_scoped(SettingScope.SYSTEM, SYSTEM_SCOPE_ID, "host.secret_key")
    resolved = await service.resolve("host.secret_key")
    listed = [s for s in await service.list_all() if s.key == "host.secret_key"]
    by_scope = [
        s
        for s in await service.list_by_scope(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        if s.key == "host.secret_key"
    ]

    for label, out in (
        ("get_by_id", by_id),
        ("get_scoped", scoped),
        ("resolve", resolved),
        ("list_all", listed[0]),
        ("list_by_scope", by_scope[0]),
    ):
        assert out is not None, f"{label} returned nothing"
        assert out.value == SENSITIVE_PLACEHOLDER, f"{label} leaked the secret"


async def test_an_ordinary_setting_is_untouched(db_session) -> None:
    """Guards against over-masking: only the named keys are hidden."""
    service = SettingService(db_session)
    await service.create(
        SettingCreate(
            scope=SettingScope.SYSTEM,
            scope_id=SYSTEM_SCOPE_ID,
            key="host.log_level",
            value="DEBUG",
            value_type="string",
        )
    )
    await db_session.commit()

    resolved = await service.resolve("host.log_level")

    assert resolved is not None
    assert resolved.value == "DEBUG"


async def test_the_stored_row_still_holds_the_real_value(db_session) -> None:
    """Masking is a serialization concern, not a write one — the boot-time
    reader goes straight to SQL and must still find the real key."""
    from sqlalchemy import text

    await _seed_secret(db_session)

    row = (
        await db_session.execute(
            text("SELECT value FROM settings_setting WHERE key = 'host.secret_key'")
        )
    ).first()

    assert row is not None
    assert row[0] == _REAL
