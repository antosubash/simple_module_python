"""The ``signup`` shared prop drives whether a "Sign up" link is rendered.

``/users/register`` raises 404 when ``allow_signup`` is off, so the public shell
has to know the answer before it draws the link. Getting the default wrong in
either direction is a visible bug: too eager and every visitor hits a 404, too
shy and a genuinely open instance hides its own signup.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from users.shared_props import users_shared_props


def _request(users_state: object) -> SimpleNamespace:
    """A stand-in carrying only what the provider is allowed to touch."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(users=users_state)))


class TestSignupSharedProp:
    @pytest.mark.parametrize("allow", [True, False])
    def test_reflects_the_setting(self, allow: bool) -> None:
        request = _request(SimpleNamespace(settings=SimpleNamespace(allow_signup=allow)))
        assert users_shared_props(request) == {"signup": {"allowed": allow}}

    def test_coerces_to_a_real_bool(self) -> None:
        """The value is serialised straight to JSON, so it must not leak a
        truthy non-bool into the page props."""
        request = _request(SimpleNamespace(settings=SimpleNamespace(allow_signup=1)))
        assert users_shared_props(request)["signup"]["allowed"] is True

    def test_defaults_closed_when_settings_are_missing(self) -> None:
        request = _request(SimpleNamespace())
        assert users_shared_props(request) == {"signup": {"allowed": False}}

    def test_defaults_closed_when_module_state_is_absent(self) -> None:
        """Never raises: the provider runs on every request and a failure here
        would cost the whole page, not just the link."""
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        assert users_shared_props(request) == {"signup": {"allowed": False}}


class TestProviderIsRegistered:
    def test_the_built_app_carries_it(self, app) -> None:
        """Registered during ``register_settings``, so a fully booted app has it
        in place before the first request is served. Asserted against the real
        app rather than a bare FastAPI: the registration sits downstream of the
        settings module, and a stub would pass while the wiring was broken."""
        providers = getattr(app.state, "inertia_shared_providers", [])
        assert users_shared_props in providers
