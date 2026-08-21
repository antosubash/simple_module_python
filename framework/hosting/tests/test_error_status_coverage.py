"""Every status the handler renders must have copy on the page.

The Inertia error page keys its title/description/accent off the numeric
status. A status the handler renders but the page has no row for falls back
to a bare "Error / An unexpected error occurred" — which is worse than the
generic message suggests, because the user is told nothing actionable. These
two lists live in different languages, so nothing but a test keeps them
honest.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from simple_module_hosting._error_handlers import (
    _INERTIA_ERROR_STATUSES,
    _SIGN_IN_STATUSES,
    _login_url,
)

_ERROR_PAGE = Path(__file__).resolve().parents[3] / "host" / "client_app" / "pages" / "Error.tsx"


def _statuses_with_copy() -> set[int]:
    """Numeric keys of the status table in Error.tsx."""
    source = _ERROR_PAGE.read_text(encoding="utf-8")
    table = re.search(
        r"const table: Record<number, StatusCopy> = \{(.*?)\n  \};", source, re.DOTALL
    )
    assert table, "status table not found in Error.tsx — did its shape change?"
    return {int(m) for m in re.findall(r"^    (\d{3}):", table.group(1), re.MULTILINE)}


class TestStatusCopyParity:
    def test_error_page_exists(self) -> None:
        assert _ERROR_PAGE.is_file(), _ERROR_PAGE

    def test_every_rendered_status_has_copy(self) -> None:
        missing = _INERTIA_ERROR_STATUSES - _statuses_with_copy()
        assert not missing, (
            f"statuses rendered by the handler with no copy in Error.tsx: {sorted(missing)}"
        )

    def test_sign_in_statuses_are_rendered_statuses(self) -> None:
        """Offering a sign-in button on a status that never reaches the page
        would be dead code."""
        assert _SIGN_IN_STATUSES <= _INERTIA_ERROR_STATUSES

    @pytest.mark.parametrize("status", [401, 403, 404, 419, 422, 429, 500, 503])
    def test_expected_statuses_are_covered(self, status: int) -> None:
        assert status in _INERTIA_ERROR_STATUSES


class TestErrorCopyIsReachable:
    """Every host.error.* string must actually be rendered by something.

    Adding a status's copy and forgetting to wire it leaves a key that no
    code path can reach — the page silently shows the generic message
    instead. That is how ``maintenance_title`` was dead on arrival: the 503
    branch existed, but nothing ever selected the maintenance wording.
    """

    def test_every_error_key_is_referenced(self) -> None:
        import json

        locales = _ERROR_PAGE.parents[3] / "host" / "locales" / "en.json"
        catalog = json.loads(locales.read_text(encoding="utf-8"))["error"]
        source = _ERROR_PAGE.read_text(encoding="utf-8")

        # Two spellings in the page: the `keys.host.error.x` path, and the
        # `e.x` alias the status table uses.
        unreferenced = sorted(
            k for k in catalog if f"e.{k}" not in source and f"keys.host.error.{k}" not in source
        )
        assert not unreferenced, (
            "host.error keys with no reference in Error.tsx — either render "
            f"them or delete them: {unreferenced}"
        )


class _StubRequest:
    def __init__(self, provider: object | None) -> None:
        class _AuthState:
            auth_provider = provider

        class _State:
            auth = _AuthState() if provider is not None else None

        class _App:
            state = _State()

        self.app = _App()


class TestLoginUrlLookup:
    def test_returns_provider_url(self) -> None:
        class _Provider:
            def get_login_url(self, request, next_url=None):
                return "/users/login"

        assert _login_url(_StubRequest(_Provider())) == "/users/login"

    def test_no_auth_provider_yields_none(self) -> None:
        """An app with no auth module installed simply gets no sign-in button."""
        assert _login_url(_StubRequest(None)) is None

    def test_broken_provider_does_not_raise(self) -> None:
        """An error page that itself errors is the worst possible outcome."""

        class _Exploding:
            def get_login_url(self, request, next_url=None):
                raise RuntimeError("provider is down")

        assert _login_url(_StubRequest(_Exploding())) is None


class TestRenderFallback:
    """render_error_page must never raise — it is the last line of defence."""

    async def test_half_built_app_falls_back_to_json(self) -> None:
        """``app.state.sm`` is missing while the app is still assembling. That
        lookup used to sit outside the try, so the documented JSON fallback
        never ran and the error page raised while reporting an error."""
        from simple_module_hosting._error_handlers import render_error_page
        from starlette.applications import Starlette
        from starlette.requests import Request

        app = Starlette()
        request = Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "path": "/boom",
                "raw_path": b"/boom",
                "query_string": b"",
                "scheme": "http",
                "server": ("testserver", 80),
                "client": ("testclient", 1234),
                "headers": [],
                "app": app,
            }
        )

        resp = await render_error_page(request, 500, "kaboom")

        assert resp.status_code == 500
        assert b"kaboom" in resp.body
