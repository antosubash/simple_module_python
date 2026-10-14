"""GH #468: timezone-aware columns must read back aware on SQLite.

SQLite stores no offset, so a plain ``DateTime(timezone=True)`` column reads
back naive and pydantic serializes it without one — the browser then parses
UTC as local time. ``AwareDateTime`` attaches UTC on read.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import sqlalchemy as sa
from simple_module_db import AuditMixin, AwareDateTime, render_item
from sqlalchemy.ext.asyncio import create_async_engine

_md = sa.MetaData()
_stamps = sa.Table(
    "aware_dt_stamps",
    _md,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("at", AwareDateTime()),
)


async def _roundtrip(value: datetime) -> datetime:
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_md.create_all)
            await conn.execute(_stamps.insert().values(id=1, at=value))
            return (await conn.execute(sa.select(_stamps.c.at))).scalar_one()
    finally:
        await engine.dispose()


async def test_aware_value_reads_back_aware_utc():
    stamp = datetime(2026, 10, 14, 10, 40, 52, 123456, tzinfo=UTC)

    loaded = await _roundtrip(stamp)

    assert loaded == stamp
    assert loaded.utcoffset() == timedelta(0)
    assert loaded.isoformat().endswith("+00:00")


async def test_non_utc_offset_is_normalised_to_utc():
    stamp = datetime(2026, 10, 14, 12, 40, tzinfo=timezone(timedelta(hours=2)))

    loaded = await _roundtrip(stamp)

    assert loaded == stamp
    assert loaded.tzinfo == UTC
    assert loaded.hour == 10


async def test_naive_value_is_taken_as_utc():
    """Unlike SQLModel's ``UTCDateTime``, a naive bind is accepted as UTC."""
    loaded = await _roundtrip(datetime(2026, 10, 14, 10, 40))

    assert loaded == datetime(2026, 10, 14, 10, 40, tzinfo=UTC)


def test_audit_mixin_columns_use_aware_type():
    fields = AuditMixin.model_fields
    for name in ("created_at", "updated_at"):
        sa_type = getattr(fields[name], "sa_type", None)
        assert isinstance(sa_type, AwareDateTime), name


def test_renders_as_plain_timezone_datetime():
    """Adopting the type must not make autogenerate emit a diff or a sqlmodel import."""
    ctx = SimpleNamespace(imports=set())

    assert render_item("type", AwareDateTime(), ctx) == "sa.DateTime(timezone=True)"
    assert ctx.imports == set()
