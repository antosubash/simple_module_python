"""Usage metering seam: consumers depend on this contract, never on billing.

A provider installs itself as ``app.state.tenants.usage``. Without one,
``UnlimitedUsageMeter`` allows everything and keeps no usage state.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import uuid4

if TYPE_CHECKING:
    from fastapi import FastAPI


@dataclass(frozen=True, slots=True)
class UsageOutcome:
    """A usage decision; ``used`` is the total observed when returning.

    Successful consumption includes the consumed quantity in ``used``.
    ``requested`` describes this operation and is not subtracted again from
    ``remaining``. ``None`` for ``limit`` means unlimited; ``resets_at`` is
    absent for meters without a scheduled reset.
    """

    meter: str
    allowed: bool
    limit: int | None
    used: int
    requested: int
    resets_at: datetime | None

    @property
    def remaining(self) -> int | None:
        """Available capacity, floored at zero; ``None`` means unlimited."""
        return None if self.limit is None else max(0, self.limit - self.used)


@dataclass(frozen=True, slots=True)
class UsageReservation:
    """An opaque hold owned by the provider that issued it."""

    id: str
    meter: str
    quantity: int
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class UsageSummaryRow:
    """One meter's current usage and limit."""

    meter: str
    used: int
    limit: int | None
    resets_at: datetime | None


class UsageExceededError(Exception):
    """A rejected usage decision; implementers may map this to HTTP 402."""

    def __init__(self, outcome: UsageOutcome) -> None:
        super().__init__(f"Usage limit reached for '{outcome.meter}' ({outcome.limit})")
        self.outcome = outcome


@runtime_checkable
class UsageMeter(Protocol):
    """Async usage operations keyed by tenant and meter (e.g. ``jobs.concurrent``).

    Persistence, period boundaries, idempotency and reservation lifecycle belong
    to the provider. Consumers pass reservations back to the issuing provider.
    """

    async def check(self, tenant_id: str, meter: str, quantity: int = 1) -> UsageOutcome:
        """Check capacity without recording usage or reserving it."""
        ...

    async def consume(
        self, tenant_id: str, meter: str, quantity: int = 1, *, idempotency_key: str | None = None
    ) -> UsageOutcome:
        """Atomically check and increment; a denial records nothing."""
        ...

    async def record(
        self, tenant_id: str, meter: str, quantity: int, *, idempotency_key: str | None = None
    ) -> None:
        """Record after-the-fact usage unconditionally, even over the limit."""
        ...

    async def refund(
        self, tenant_id: str, meter: str, quantity: int, *, idempotency_key: str | None = None
    ) -> None:
        """Return previously recorded usage."""
        ...

    async def reserve(
        self, tenant_id: str, meter: str, quantity: int = 1, *, ttl: timedelta | None = None
    ) -> UsageReservation | None:
        """Atomically hold capacity, or return ``None`` when it would exceed."""
        ...

    async def commit(self, reservation: UsageReservation) -> None:
        """Convert a hold into recorded usage."""
        ...

    async def release(self, reservation: UsageReservation) -> None:
        """Return held capacity without recording usage."""
        ...

    async def summary(self, tenant_id: str) -> Sequence[UsageSummaryRow]:
        """Return the tenant's per-meter usage totals."""
        ...


class UnlimitedUsageMeter:
    """Default provider: unlimited capacity and no accounting or stored holds."""

    async def check(self, tenant_id: str, meter: str, quantity: int = 1) -> UsageOutcome:
        return UsageOutcome(meter, True, None, 0, quantity, None)

    async def consume(
        self, tenant_id: str, meter: str, quantity: int = 1, *, idempotency_key: str | None = None
    ) -> UsageOutcome:
        return await self.check(tenant_id, meter, quantity)

    async def record(
        self, tenant_id: str, meter: str, quantity: int, *, idempotency_key: str | None = None
    ) -> None:
        pass

    async def refund(
        self, tenant_id: str, meter: str, quantity: int, *, idempotency_key: str | None = None
    ) -> None:
        pass

    async def reserve(
        self, tenant_id: str, meter: str, quantity: int = 1, *, ttl: timedelta | None = None
    ) -> UsageReservation:
        expires_at = datetime.now(UTC) + ttl if ttl is not None else None
        return UsageReservation(str(uuid4()), meter, quantity, expires_at)

    async def commit(self, reservation: UsageReservation) -> None:
        pass

    async def release(self, reservation: UsageReservation) -> None:
        pass

    async def summary(self, tenant_id: str) -> Sequence[UsageSummaryRow]:
        return []


def get_usage_meter(app: FastAPI) -> UsageMeter:
    """The tenants usage provider, or an unlimited fallback when absent."""
    provider = getattr(getattr(app.state, "tenants", None), "usage", None)
    return provider if provider is not None else UnlimitedUsageMeter()
