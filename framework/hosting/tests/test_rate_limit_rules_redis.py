"""Per-route rules counted in a real Redis: workers share one budget (#529)."""

from __future__ import annotations

import uuid

from simple_module_core.rate_limit import RateSpec
from simple_module_hosting._rate_limit_store import RedisWindowStore


async def test_two_stores_share_one_user_budget(redis_server) -> None:
    # Two stores = two workers; a per-test bucket name keeps xdist workers apart.
    bucket = f"rule:prefix:POST:/api/x:user=alice-{uuid.uuid4().hex}"
    spec = RateSpec(3, 60)
    first = RedisWindowStore.from_url(redis_server)
    second = RedisWindowStore.from_url(redis_server)
    try:
        results = [await first.hit(bucket, spec), await second.hit(bucket, spec)]
        results += [await first.hit(bucket, spec), await second.hit(bucket, spec)]
        other = await second.hit(bucket.replace("alice", "bob"), spec)
    finally:
        await first.reset(bucket)
    assert [r.allowed for r in results] == [True, True, True, False]
    assert 1 <= results[-1].retry_after <= 60
    assert other.allowed
