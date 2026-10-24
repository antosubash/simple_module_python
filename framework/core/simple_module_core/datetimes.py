"""UTC timestamps and normalization of legacy naive database values."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    """Interpret a naive value as UTC; preserve an existing timezone."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
