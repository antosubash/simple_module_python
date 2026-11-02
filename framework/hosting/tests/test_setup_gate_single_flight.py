"""SetupMiddleware refreshes its verdict single-flight.

Under load, every request that found the cached verdict expired used to run the
setup steps itself — each a session checkout and a ``COUNT(*)`` — and behind a
saturated pool those queued for seconds and starved real work. See
``SetupMiddleware._is_complete``; the TTL/caching rules are in
``test_setup_gate``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from simple_module_core.setup_steps import SetupRegistry, SetupStep


def _scope() -> dict:
    return {"type": "http", "path": "/dashboard", "method": "GET", "headers": [], "app": None}


async def _status(middleware, registry) -> int:
    scope = _scope()
    sm = SimpleNamespace(setup_registry=registry)
    scope["app"] = SimpleNamespace(state=SimpleNamespace(sm=sm))
    sent: dict = {}

    async def send(message):
        if message["type"] == "http.response.start":
            sent.update(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)
    return sent["status"]


async def _passthrough(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


class _GatedStep:
    """A step whose evaluation blocks until released, counting evaluations."""

    def __init__(self, result: bool) -> None:
        self.result = result
        self.calls = 0
        self.release = asyncio.Event()

    async def __call__(self, _app) -> bool:
        self.calls += 1
        await self.release.wait()
        return self.result

    def registry(self) -> SetupRegistry:
        registry = SetupRegistry()
        registry.add(SetupStep(id="users.administrator", title="admin", is_complete=self))
        return registry


async def test_concurrent_requests_share_one_evaluation() -> None:
    from simple_module_hosting.setup_gate import SetupMiddleware

    step = _GatedStep(result=True)
    registry = step.registry()
    middleware = SetupMiddleware(_passthrough)

    pending = [asyncio.ensure_future(_status(middleware, registry)) for _ in range(20)]
    await asyncio.sleep(0)
    step.release.set()

    assert await asyncio.gather(*pending) == [200] * 20
    assert step.calls == 1, f"each waiting request ran the steps itself ({step.calls}x)"


async def test_an_expired_complete_verdict_answers_while_it_refreshes() -> None:
    """Requests must not queue behind the refresh's database checkout."""
    from simple_module_hosting.setup_gate import SetupMiddleware

    step = _GatedStep(result=True)
    step.release.set()
    registry = step.registry()
    middleware = SetupMiddleware(_passthrough)
    assert await _status(middleware, registry) == 200

    middleware._verdict_expires = 0.0  # the TTL lapses
    step.release.clear()
    refreshing = asyncio.ensure_future(_status(middleware, registry))
    for _ in range(10):  # let the refresh start and block
        if step.calls == 2:
            break
        await asyncio.sleep(0)
    assert step.calls == 2

    # Answered from the stale verdict, without waiting for the blocked refresh.
    assert await asyncio.wait_for(_status(middleware, registry), timeout=1) == 200
    assert step.calls == 2

    step.release.set()
    assert await refreshing == 200


async def test_a_refresh_that_finds_setup_incomplete_brings_the_wizard_back() -> None:
    """Serving stale while refreshing must not hide a lost administrator."""
    from simple_module_hosting.setup_gate import SetupMiddleware

    step = _GatedStep(result=True)
    step.release.set()
    registry = step.registry()
    middleware = SetupMiddleware(_passthrough)
    assert await _status(middleware, registry) == 200

    middleware._verdict_expires = 0.0
    step.result = False  # the last administrator was deactivated

    assert await _status(middleware, registry) == 302
    assert await _status(middleware, registry) == 302


async def test_a_cancelled_caller_does_not_cancel_the_shared_refresh() -> None:
    from simple_module_hosting.setup_gate import SetupMiddleware

    step = _GatedStep(result=True)
    registry = step.registry()
    middleware = SetupMiddleware(_passthrough)

    first = asyncio.ensure_future(_status(middleware, registry))
    second = asyncio.ensure_future(_status(middleware, registry))
    await asyncio.sleep(0)
    first.cancel()  # the client that started the refresh went away
    await asyncio.sleep(0)
    step.release.set()

    assert await second == 200
    assert step.calls == 1
