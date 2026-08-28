"""SetupMiddleware: what a request hits while the install is not set up.

The registry it consults is covered in ``test_setup_registry``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from simple_module_core.setup_steps import SetupRegistry, SetupStep


def _step(step_id: str, done: bool, *, required: bool = True, order: int = 100) -> SetupStep:
    async def is_complete(_app) -> bool:
        return done

    return SetupStep(
        id=step_id, title=step_id, is_complete=is_complete, required=required, order=order
    )


def _scope(path: str, headers: list | None = None) -> dict:
    return {
        "type": "http",
        "path": path,
        "method": "GET",
        "headers": headers or [],
        "app": None,
    }


async def _run(middleware, scope) -> dict:
    """Drive the ASGI callable and capture the response start message."""
    sent: dict = {}

    async def send(message):
        if message["type"] == "http.response.start":
            sent.update(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)
    return sent


async def _passthrough(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _app_with(registry):
    return SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(setup_registry=registry)))


@pytest.mark.parametrize(
    "path", ["/setup", "/setup/administrator", "/static/app.css", "/health/ready"]
)
async def test_exempt_paths_pass_through(path: str) -> None:
    """The wizard, its assets and the probes must answer during setup —
    redirecting /static to HTML breaks the page reporting the problem."""
    from simple_module_hosting.setup_gate import SetupMiddleware

    registry = SetupRegistry()
    registry.add(_step("users.administrator", done=False))
    scope = _scope(path)
    scope["app"] = _app_with(registry)

    assert (await _run(SetupMiddleware(_passthrough), scope))["status"] == 200


async def test_redirects_while_incomplete() -> None:
    from simple_module_hosting.setup_gate import SetupMiddleware

    registry = SetupRegistry()
    registry.add(_step("users.administrator", done=False))
    scope = _scope("/dashboard")
    scope["app"] = _app_with(registry)

    result = await _run(SetupMiddleware(_passthrough), scope)

    assert result["status"] == 302
    assert (b"location", b"/setup") in [(k.lower(), v) for k, v in result["headers"]]


async def test_releases_once_complete() -> None:
    from simple_module_hosting.setup_gate import SetupMiddleware

    registry = SetupRegistry()
    registry.add(_step("users.administrator", done=True))
    scope = _scope("/dashboard")
    scope["app"] = _app_with(registry)

    assert (await _run(SetupMiddleware(_passthrough), scope))["status"] == 200


async def test_never_engages_with_no_registered_steps() -> None:
    """The Keycloak install must reach its own app."""
    from simple_module_hosting.setup_gate import SetupMiddleware

    scope = _scope("/dashboard")
    scope["app"] = _app_with(SetupRegistry())

    assert (await _run(SetupMiddleware(_passthrough), scope))["status"] == 200


async def test_an_incomplete_verdict_is_never_cached() -> None:
    """The gate must release on the very next request after setup completes.

    The middleware caches its verdict to avoid a session checkout and a
    COUNT(*) on every request of a configured install's life. Caching the
    *negative* would strand the operator at the moment it matters: the wizard
    creates the administrator and sends the browser to `/`, a stale negative
    redirects that to `/setup`, and `/setup` has just started returning 404.
    """
    from simple_module_hosting.setup_gate import SetupMiddleware

    complete = False

    async def is_complete(_app) -> bool:
        return complete

    registry = SetupRegistry()
    registry.add(SetupStep(id="users.administrator", title="admin", is_complete=is_complete))

    middleware = SetupMiddleware(_passthrough)
    scope = _scope("/dashboard")
    scope["app"] = _app_with(registry)

    assert (await _run(middleware, scope))["status"] == 302

    complete = True  # what creating the administrator does
    scope2 = _scope("/dashboard")
    scope2["app"] = _app_with(registry)

    assert (await _run(middleware, scope2))["status"] == 200, (
        "a cached 'incomplete' verdict stranded the operator on a dead page"
    )


async def test_a_complete_verdict_is_cached() -> None:
    """The half that is worth caching: a configured install should not pay for
    the check on every request forever."""
    from simple_module_hosting.setup_gate import SetupMiddleware

    calls = 0

    async def is_complete(_app) -> bool:
        nonlocal calls
        calls += 1
        return True

    registry = SetupRegistry()
    registry.add(SetupStep(id="users.administrator", title="admin", is_complete=is_complete))

    middleware = SetupMiddleware(_passthrough)
    for _ in range(3):
        scope = _scope("/dashboard")
        scope["app"] = _app_with(registry)
        assert (await _run(middleware, scope))["status"] == 200

    assert calls == 1, f"expected the positive verdict to be reused, ran the steps {calls}x"


async def test_inertia_request_gets_409_location() -> None:
    """Inertia's client follows a 302 with an XHR and chokes on the wizard's
    HTML; 409 + X-Inertia-Location tells it to do a full page visit."""
    from simple_module_hosting.setup_gate import SetupMiddleware

    registry = SetupRegistry()
    registry.add(_step("users.administrator", done=False))
    scope = _scope("/dashboard", headers=[(b"x-inertia", b"true")])
    scope["app"] = _app_with(registry)

    result = await _run(SetupMiddleware(_passthrough), scope)

    assert result["status"] == 409
    headers = {k.lower(): v for k, v in result["headers"]}
    assert headers[b"x-inertia-location"] == b"/setup"


@pytest.mark.parametrize(
    "path,exempt",
    [
        ("/setup", True),
        ("/setup/", True),
        ("/setup/administrator", True),
        ("/static/app.css", True),
        ("/health", True),
        ("/health/ready", True),
        # The bypass: a bare "/setup" prefix match also exempts an unrelated
        # module route that merely starts with those six characters.
        ("/setup-guide", False),
        ("/staticky", False),
        ("/healthcheck-admin", False),
    ],
)
async def test_exemptions_match_exactly(path: str, exempt: bool) -> None:
    """Mirrored by attach_public_routes, where a sloppy match is an auth
    bypass rather than a missed redirect."""
    from simple_module_hosting.setup_gate import SetupMiddleware

    registry = SetupRegistry()
    registry.add(_step("users.administrator", done=False))
    scope = _scope(path)
    scope["app"] = _app_with(registry)

    status = (await _run(SetupMiddleware(_passthrough), scope))["status"]

    assert (status == 200) is exempt, f"{path} exempt={status == 200}, expected {exempt}"


async def test_incomplete_all_includes_optional_steps() -> None:
    """What the wizard displays, versus what the gate acts on.

    incomplete() only ever walks required_steps, so using it for the display
    renders every optional step with a checkmark whatever its predicate says.
    """
    registry = SetupRegistry()
    registry.add(_step("required.done", done=True))
    registry.add(_step("optional.pending", done=False, required=False))

    assert [s.id for s in await registry.incomplete(None)] == []
    assert [s.id for s in await registry.incomplete_all(None)] == ["optional.pending"]
