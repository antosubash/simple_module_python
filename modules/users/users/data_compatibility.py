"""Recognize legacy bearer-token columns and credentials without reading secrets out."""

from simple_module_core.data_compatibility import DataCompatibilityIssue
from sqlalchemy import String, column, func, inspect, or_, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from users.constants import UPGRADE_HASHED_BEARER_TOKENS
from users.models import RefreshToken, UserAccessToken

# A SHA-256 hex digest; tokens hashed at rest (#626) are always this long.
_DIGEST_LENGTH = 64
_SAMPLE = 100


async def check_data_compatibility(db: AsyncSession) -> list[DataCompatibilityIssue]:
    connection = await db.connection()
    for model in (RefreshToken, UserAccessToken):
        name = model.__tablename__

        def token_type(sync, name=name):
            inspector = inspect(sync)
            if not inspector.has_table(name):
                return None
            return next(
                (c["type"] for c in inspector.get_columns(name) if c["name"] == "token"), None
            )

        kind = await connection.run_sync(token_type)
        if kind is None:
            # Not migrated yet: the migration check owns that, not this one.
            continue
        # Only a column too short for a digest is wrong; TEXT or a wider VARCHAR
        # from a hand-ported revision holds hashes just as well.
        length = getattr(kind, "length", None)
        if not isinstance(kind, String) or (length is not None and length < _DIGEST_LENGTH):
            return _incompatible()
        # One probe, not a scan into Python: boot runs this every time. Stripping
        # the hex digits with nested replace() is portable (SQLite has no regex);
        # anything left over, or the wrong length, is a pre-hashing token.
        # A sample, not the table: un-hashed tokens come from a skipped upgrade,
        # so every old row is plaintext and the first few show it.
        token = select(table(name, column("token")).c.token).limit(_SAMPLE).subquery().c.token
        leftover = token
        for digit in "0123456789abcdef":
            leftover = func.replace(leftover, digit, "")
        legacy = await db.scalar(
            select(1).where(or_(func.length(token) != _DIGEST_LENGTH, leftover != "")).limit(1)
        )
        if legacy is not None:
            return _incompatible()
    return []


def _incompatible() -> list[DataCompatibilityIssue]:
    return [
        DataCompatibilityIssue(
            upgrade_id=UPGRADE_HASHED_BEARER_TOKENS,
            message="Bearer-token schema or credentials predate hashing at rest. "
            "Stop all old workers and apply the token invalidation/column upgrade; "
            "clients must sign in again.",
            severity="error",
        )
    ]
