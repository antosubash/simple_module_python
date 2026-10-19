"""The host rate-limit store is shared with modules and readable without counting (#530)."""

from __future__ import annotations

from simple_module_core.rate_limit import InProcessWindowStore, RateSpec
from simple_module_core.services import Services
from simple_module_hosting._rate_limit import RateLimitMiddleware, RedisWindowStore


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


async def test_peek_does_not_count() -> None:
    store = InProcessWindowStore(clock=_Clock())
    spec = RateSpec(2, 60)
    assert (await store.peek("k", spec)).count == 0
    await store.hit("k", spec)
    await store.hit("k", spec)
    first = await store.peek("k", spec)
    second = await store.peek("k", spec)
    assert (first.count, first.allowed) == (2, False)
    assert second.count == 2


async def test_peek_allows_while_under_the_limit() -> None:
    store = InProcessWindowStore(clock=_Clock())
    spec = RateSpec(2, 60)
    await store.hit("k", spec)
    assert (await store.peek("k", spec)).allowed is True


async def test_peek_window_expires() -> None:
    clock = _Clock()
    store = InProcessWindowStore(clock=clock)
    spec = RateSpec(1, 60)
    await store.hit("k", spec)
    assert (await store.peek("k", spec)).retry_after == 60
    clock.now += 61
    result = await store.peek("k", spec)
    assert (result.count, result.allowed, result.retry_after) == (0, True, 0)


class _FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def eval(self, script: str, numkeys: int, key: str, *args):
        if args:  # hit: INCR + PEXPIRE
            self.counts[key] = self.counts.get(key, 0) + 1
            return [self.counts[key], args[0]]
        count = self.counts.get(key)
        return [0, 0] if count is None else [count, 30_000]


class _DeadRedis:
    async def eval(self, *a, **k):
        raise ConnectionError("redis down")


async def test_redis_peek_reads_without_counting() -> None:
    redis = _FakeRedis()
    store = RedisWindowStore(redis)
    spec = RateSpec(1, 60)
    assert (await store.peek("k", spec)).allowed is True
    await store.hit("k", spec)
    result = await store.peek("k", spec)
    assert (result.count, result.allowed, result.retry_after) == (1, False, 30)
    assert redis.counts == {"sm:rl:k": 1}


async def test_peek_falls_back_when_redis_down() -> None:
    store = RedisWindowStore(_DeadRedis())
    spec = RateSpec(1, 60)
    await store.hit("k", spec)  # counted by the per-worker fallback
    assert (await store.peek("k", spec)).allowed is False


def test_services_default_store() -> None:
    factory = Services.__dataclass_fields__["rate_limit_store"].default_factory
    assert isinstance(factory(), InProcessWindowStore)  # ty: ignore[call-non-callable]


async def test_create_app_shares_one_store(app) -> None:
    [guard] = [m for m in app.user_middleware if m.cls is RateLimitMiddleware]
    assert guard.kwargs["store"] is app.state.sm.rate_limit_store


async def test_sliding_hit_restarts_the_window() -> None:
    clock = _Clock()
    store = InProcessWindowStore(clock=clock)
    spec = RateSpec(10, 60)
    await store.hit("k", spec, sliding=True)
    clock.now += 50
    await store.hit("k", spec, sliding=True)  # pushes the end to now + 60
    clock.now += 50  # 100s after the first hit, 50s after the last
    assert (await store.hit("k", spec, sliding=True)).count == 3
    clock.now += 61
    assert (await store.hit("k", spec, sliding=True)).count == 1


async def test_fixed_hit_does_not_slide() -> None:
    clock = _Clock()
    store = InProcessWindowStore(clock=clock)
    spec = RateSpec(10, 60)
    await store.hit("k", spec)
    clock.now += 50
    await store.hit("k", spec)
    clock.now += 50
    assert (await store.hit("k", spec)).count == 1


async def test_reset_forgets_the_window() -> None:
    store = InProcessWindowStore(clock=_Clock())
    spec = RateSpec(1, 60)
    await store.hit("k", spec)
    await store.reset("k")
    assert (await store.peek("k", spec)).count == 0


async def test_redis_sliding_flag_and_reset() -> None:
    calls: list[tuple] = []

    class _Recording(_FakeRedis):
        async def eval(self, script: str, numkeys: int, key: str, *args):
            calls.append((script, args))
            if "DEL" in script:
                self.counts.pop(key, None)
                return 0
            return await super().eval(script, numkeys, key, *args)

    store = RedisWindowStore(_Recording())
    await store.hit("k", RateSpec(5, 60), sliding=True)
    assert calls[-1][1] == (60_000, "1")
    await store.hit("k", RateSpec(5, 60))
    assert calls[-1][1] == (60_000,)
    await store.reset("k")
    assert (await store.peek("k", RateSpec(5, 60))).count == 0


def test_script_slides_on_flag() -> None:
    from simple_module_hosting._rate_limit import _LUA

    assert "ARGV[2] == '1'" in _LUA
