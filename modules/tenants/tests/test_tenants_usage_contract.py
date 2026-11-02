"""Public usage contracts and the default, unlimited provider."""

from collections.abc import Sequence
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from tenants.contracts import (
    UnlimitedUsageMeter,
    UsageExceededError,
    UsageMeter,
    UsageOutcome,
    UsageReservation,
    UsageSummaryRow,
    get_usage_meter,
)
from tenants.module import TenantsModule
from tenants.services import TenantsServices
from tenants.settings import TenantsSettings


class FakeUsageMeter:
    """An independent provider needs no inheritance from the contract."""

    async def check(self, tenant_id: str, meter: str, quantity: int = 1) -> UsageOutcome:
        return UsageOutcome(meter, False, 0, 0, quantity, None)

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
    ) -> UsageReservation | None:
        return None

    async def commit(self, reservation: UsageReservation) -> None:
        pass

    async def release(self, reservation: UsageReservation) -> None:
        pass

    async def summary(self, tenant_id: str) -> Sequence[UsageSummaryRow]:
        return [UsageSummaryRow("jobs.concurrent", 0, 0, None)]


def test_runtime_protocol_conformance():
    default: UsageMeter = UnlimitedUsageMeter()
    fake: UsageMeter = FakeUsageMeter()
    assert isinstance(default, UsageMeter)
    assert isinstance(fake, UsageMeter)
    assert not isinstance(object(), UsageMeter)


@pytest.mark.parametrize(
    "limit,used,remaining", [(None, 9, None), (10, 3, 7), (0, 0, 0), (2, 3, 0)]
)
def test_outcome_remaining(limit, used, remaining):
    outcome = UsageOutcome("jobs.concurrent", True, limit, used, 1, None)
    assert outcome.remaining == remaining


@pytest.mark.parametrize(
    "value",
    [
        UsageOutcome("jobs.concurrent", True, None, 0, 1, None),
        UsageReservation("hold-1", "jobs.concurrent", 1, None),
        UsageSummaryRow("jobs.concurrent", 0, None, None),
    ],
)
def test_value_objects_are_frozen(value):
    with pytest.raises(FrozenInstanceError):
        value.meter = "changed"
    assert not hasattr(value, "__dict__")


def test_exceeded_error_carries_outcome():
    outcome = UsageOutcome("jobs.concurrent", False, 5, 5, 1, None)
    error = UsageExceededError(outcome)
    assert error.outcome is outcome
    assert outcome.meter in str(error)


async def test_unlimited_operations():
    provider: UsageMeter = UnlimitedUsageMeter()
    for quantity in (1, 100):
        expected = UsageOutcome("jobs.concurrent", True, None, 0, quantity, None)
        assert await provider.check("tenant-1", "jobs.concurrent", quantity) == expected
        assert (
            await provider.consume(
                "tenant-1", "jobs.concurrent", quantity, idempotency_key="consume-1"
            )
            == expected
        )
    assert (
        await provider.record("tenant-1", "jobs.concurrent", 4, idempotency_key="record-1") is None
    )
    assert (
        await provider.refund("tenant-1", "jobs.concurrent", 2, idempotency_key="refund-1") is None
    )
    assert await provider.summary("tenant-1") == []
    assert (await provider.check("tenant-1", "jobs.concurrent")).used == 0
    assert (await provider.consume("tenant-1", "jobs.concurrent")).requested == 1


async def test_unlimited_reservations():
    provider = UnlimitedUsageMeter()
    start = datetime.now(UTC)
    reservation = await provider.reserve("tenant-1", "jobs.concurrent", 3, ttl=timedelta(minutes=5))
    end = datetime.now(UTC)
    assert reservation.meter == "jobs.concurrent"
    assert reservation.quantity == 3
    assert reservation.expires_at is not None
    assert start + timedelta(minutes=5) <= reservation.expires_at <= end + timedelta(minutes=5)
    other = await provider.reserve("tenant-1", "jobs.concurrent")
    assert reservation.id and other.id and reservation.id != other.id
    assert other.quantity == 1
    assert other.expires_at is None
    assert await provider.commit(reservation) is None
    assert await provider.release(other) is None


def test_lookup_without_tenants():
    assert isinstance(get_usage_meter(FastAPI()), UnlimitedUsageMeter)


def test_services_default_and_override():
    app = FastAPI()
    services = TenantsServices(TenantsSettings())
    app.state.tenants = services
    assert isinstance(services.usage, UnlimitedUsageMeter)
    assert get_usage_meter(app) is services.usage
    replacement = FakeUsageMeter()
    services.usage = replacement
    assert get_usage_meter(app) is replacement


def test_module_registers_usage():
    app = FastAPI()
    TenantsModule().register_settings(app)
    assert isinstance(app.state.tenants.usage, UnlimitedUsageMeter)
    assert get_usage_meter(app) is app.state.tenants.usage
