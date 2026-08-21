"""Maintenance mode gates everyone except the people who can turn it off."""

from __future__ import annotations

import httpx
import pytest
from simple_module_hosting.maintenance import MaintenanceMiddleware
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


class _User:
    def __init__(self, roles: list[str]) -> None:
        self.roles = roles


class _Provider:
    """Mirrors the AuthProvider surface MaintenanceMiddleware actually uses."""

    def __init__(self, *, explode: bool = False) -> None:
        self._explode = explode

    def get_public_paths(self):
        if self._explode:
            raise RuntimeError("provider is down")
        return (("/users/login",), ("/exact-public",))


def _build_app(
    *,
    enabled: bool,
    message: str = "",
    user: _User | None = None,
    provider: _Provider | None = _Provider(),
    public_routes=None,
) -> Starlette:
    async def ok(request):
        return PlainTextResponse("app reached")

    app = Starlette(
        routes=[
            Route("/protected", ok),
            Route("/users/login", ok),
            Route("/exact-public", ok),
            Route("/health", ok),
            Route("/api/branding/logo", ok),
            Route("/api/thing", ok),
        ]
    )

    class _HostSettings:
        maintenance_mode = enabled
        maintenance_message = message

    class _HostState:
        settings = _HostSettings()

    app.state.host = _HostState()

    class _AuthState:
        auth_provider = provider

    app.state.auth = _AuthState()
    app.state.public_routes = public_routes

    app.add_middleware(MaintenanceMiddleware)
    # Stands in for AuthMiddleware, which runs further out and is what puts the
    # resolved user on request.state. Added last so it executes first, exactly
    # as the real pipeline orders them.
    app.add_middleware(_SeedUser, user=user)
    return app


class _SeedUser:
    """Minimal stand-in for AuthMiddleware's contribution to request.state."""

    def __init__(self, app, user: _User | None) -> None:
        self.app = app
        self.user = user

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and self.user is not None:
            scope.setdefault("state", {})["user"] = self.user
        await self.app(scope, receive, send)


async def _get(app, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


async def _post(app, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post(path, **kwargs)


class TestGateClosed:
    async def test_anonymous_visitor_gets_503(self) -> None:
        resp = await _get(_build_app(enabled=True), "/protected")
        assert resp.status_code == 503

    async def test_non_admin_gets_503(self) -> None:
        app = _build_app(enabled=True, user=_User(["editor"]))
        resp = await _get(app, "/protected")
        assert resp.status_code == 503

    async def test_admin_passes_through(self) -> None:
        """Someone has to be able to reach settings and switch it back off."""
        app = _build_app(enabled=True, user=_User(["admin"]))
        resp = await _get(app, "/protected")
        assert resp.status_code == 200
        assert resp.text == "app reached"

    async def test_retry_after_is_advertised(self) -> None:
        resp = await _get(_build_app(enabled=True), "/api/thing")
        assert resp.headers.get("Retry-After")


class TestAlwaysReachable:
    async def test_health_probe_survives(self) -> None:
        """Orchestrators must not kill the pod mid-maintenance."""
        resp = await _get(_build_app(enabled=True), "/health")
        assert resp.status_code == 200

    async def test_login_prefix_stays_open(self) -> None:
        """An admin signed out when the switch flipped must still get in."""
        resp = await _get(_build_app(enabled=True), "/users/login")
        assert resp.status_code == 200

    async def test_exact_public_path_stays_open(self) -> None:
        resp = await _get(_build_app(enabled=True), "/exact-public")
        assert resp.status_code == 200


class TestGateOpen:
    async def test_disabled_is_a_no_op(self) -> None:
        resp = await _get(_build_app(enabled=False), "/protected")
        assert resp.status_code == 200

    async def test_anonymous_reaches_app_when_disabled(self) -> None:
        resp = await _get(_build_app(enabled=False, user=None), "/protected")
        assert resp.text == "app reached"


class TestDegradedDependencies:
    async def test_missing_host_state_does_not_block_traffic(self) -> None:
        """Fail open on a missing setting — a config gap must not take the
        site down, which is the exact failure this feature would cause."""

        async def ok(request):
            return PlainTextResponse("app reached")

        app = Starlette(routes=[Route("/protected", ok)])
        app.add_middleware(MaintenanceMiddleware)
        resp = await _get(app, "/protected")
        assert resp.status_code == 200

    async def test_broken_provider_still_gates(self) -> None:
        """A provider that raises must not accidentally open the gate."""
        app = _build_app(enabled=True, provider=_Provider(explode=True))
        resp = await _get(app, "/protected")
        assert resp.status_code == 503

    async def test_no_auth_provider_still_gates(self) -> None:
        app = _build_app(enabled=True, provider=None)
        resp = await _get(app, "/protected")
        assert resp.status_code == 503


class TestJsonCallers:
    async def test_api_caller_gets_json_not_html(self) -> None:
        app = _build_app(enabled=True, message="Back at 14:00 UTC")
        resp = await _get(app, "/api/thing")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Back at 14:00 UTC"

    async def test_generic_detail_when_no_message_set(self) -> None:
        resp = await _get(_build_app(enabled=True), "/api/thing")
        assert resp.json()["detail"]


@pytest.mark.parametrize("roles", [[], ["viewer"], ["admin-ish"], ["Admin"]])
async def test_only_the_exact_admin_role_bypasses(roles: list[str]) -> None:
    """Substring or case-insensitive matching here would be a privilege bug."""
    app = _build_app(enabled=True, user=_User(roles))
    resp = await _get(app, "/protected")
    assert resp.status_code == 503


class TestModulePublicRoutes:
    """A module's ``register_public_routes`` rules must also bypass the gate.

    AuthMiddleware already exempts these paths from login, so a route like
    branding's public logo/favicon GET must stay reachable during maintenance
    too — otherwise the sign-in/maintenance page itself loses its branding.
    """

    async def test_module_public_route_stays_open(self) -> None:
        from simple_module_core.public_routes import PublicRouteRegistry

        registry = PublicRouteRegistry()
        registry.add_exact("/api/branding/logo", methods=["GET"])
        resp = await _get(_build_app(enabled=True, public_routes=registry), "/api/branding/logo")
        assert resp.status_code == 200
        assert resp.text == "app reached"

    async def test_uncovered_path_still_gates(self) -> None:
        """A path with no matching rule at all is not exempted by an unrelated one."""
        from simple_module_core.public_routes import PublicRouteRegistry

        registry = PublicRouteRegistry()
        registry.add_exact("/api/branding/logo", methods=["GET"])
        app = _build_app(enabled=True, public_routes=registry)
        resp = await _get(app, "/api/thing")
        assert resp.status_code == 503

    async def test_wrong_method_on_a_covered_path_still_gates(self) -> None:
        """The rule is GET-only — a POST to the same path must not bypass."""
        from simple_module_core.public_routes import PublicRouteRegistry

        registry = PublicRouteRegistry()
        registry.add_exact("/api/branding/logo", methods=["GET"])
        app = _build_app(enabled=True, public_routes=registry)
        resp = await _post(app, "/api/branding/logo")
        assert resp.status_code == 503

    async def test_no_registry_still_gates(self) -> None:
        """A degraded/missing registry must fail closed, same as no provider."""
        resp = await _get(_build_app(enabled=True, public_routes=None), "/api/branding/logo")
        assert resp.status_code == 503
