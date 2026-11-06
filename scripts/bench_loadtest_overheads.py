"""Offline request micro-benchmarks; run with ``uv run python scripts/bench_loadtest_overheads.py``.

Median of five samples; no servers, database connections or network traffic.
Fresh statements model the query objects built for each request, rather than
repeatedly timing SQLAlchemy's memoized key on a single statement.
"""

import asyncio
import json
from base64 import b64encode
from statistics import median
from timeit import repeat

from feature_flags.contracts.schemas import FeatureFlagView
from itsdangerous import TimestampSigner
from simple_module_db._core_walk import references_plain
from simple_module_db.base import create_module_base
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_hosting.middleware import SecurityHeadersMiddleware
from simple_module_hosting.path_matching import matches_path
from simple_module_hosting.session import SessionMiddleware
from sqlalchemy import select
from sqlmodel import Field

Base = create_module_base("bench_loadtest")


class Item(Base, MultiTenantMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "bench_loadtest_item"
    id: int | None = Field(default=None, primary_key=True)


def bench(label, call, number=20000):
    samples = repeat(call, number=number, repeat=5)
    print(f"{label}: {median(samples) / number * 1e6:.3f} us")


async def response(scope, receive, send):
    # Include endpoint headers so overriding them is part of the measurement.
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"vary", b"Cookie"),
                (b"x-frame-options", b"DENY"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"{}"})


async def sink(message):
    pass


async def middleware_bench(label, app, headers):
    samples = []
    loop = asyncio.get_running_loop()
    for _ in range(5):
        start = loop.time()
        for _ in range(10000):
            await app(
                {"type": "http", "scheme": "https", "path": "/", "headers": headers}, sink, sink
            )
        samples.append((loop.time() - start) / 10000 * 1e6)
    print(f"{label}: {median(samples):.3f} us")


async def main():
    bench(
        "path match",
        lambda: matches_path("/dashboard/", exact=("/health",), prefixes=("/health/", "/static/")),
    )
    values = {
        "name": "reports",
        "description": "Reports",
        "default_enabled": False,
        "enabled": True,
        "overridden": True,
        "system_enabled": None,
    }
    bench("DTO validate", lambda: FeatureFlagView(**values))
    bench("DTO construct", lambda: FeatureFlagView.model_construct(**values))
    assert (
        FeatureFlagView(**values).model_dump()
        == FeatureFlagView.model_construct(**values).model_dump()
    )
    names = {"bench_loadtest_item"}
    decisions = {select(Item).where(Item.id == 1)._generate_cache_key().key: False}
    assert not references_plain(select(Item).where(Item.id == 1), names)
    bench("fresh ORM walk", lambda: references_plain(select(Item).where(Item.id == 1), names))
    bench("fresh ORM cache key", lambda: select(Item).where(Item.id == 1)._generate_cache_key())
    bench(
        "fresh ORM cached decision",
        lambda: decisions[select(Item).where(Item.id == 1)._generate_cache_key().key],
    )
    await middleware_bench("security wrapper", SecurityHeadersMiddleware(response), [])
    cookie = TimestampSigner("benchmark").sign(b64encode(json.dumps({"user_id": "u1"}).encode()))
    await middleware_bench(
        "unchanged session wrapper",
        SessionMiddleware(response, secret_key="benchmark"),
        [(b"cookie", b"session=" + cookie)],
    )


if __name__ == "__main__":
    asyncio.run(main())
