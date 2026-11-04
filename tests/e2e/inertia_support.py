"""Shared fixtures for the ``test_inertia_*.py`` browser tests.

Test modules import the fixtures they need::

    from tests.e2e.inertia_support import page, probes, reset_probes  # noqa: F401

They drive the development-only fixture pages under ``/__e2e/inertia``
(``host/e2e_inertia``). ``page`` is signed in through one API login per session
and fails the test on any console error or uncaught page error; the existing
e2e tests keep pytest-playwright's plain ``page``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

PREFIX = "/__e2e/inertia"


@pytest.fixture(scope="session")
def inertia_storage_state(
    playwright: Playwright,
    base_url: str,
    e2e_username: str,
    e2e_password: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> str:
    path = tmp_path_factory.mktemp("inertia-e2e") / "state.json"
    api = playwright.request.new_context(base_url=base_url)
    resp = api.post(
        "/api/users/auth/login", form={"username": e2e_username, "password": e2e_password}
    )
    assert resp.status == 204, f"login failed: {resp.status} {resp.text()}"
    api.storage_state(path=str(path))
    api.dispose()
    return str(path)


def _noise(text: str, allow_resource: bool) -> bool:
    # Browser-generated line for any 4xx/5xx subresource or navigation; only
    # tests that deliberately provoke those opt in.
    if allow_resource and "Failed to load resource" in text:
        return True
    # React DevTools hint printed by the dev build; not an application error.
    return "Download the React DevTools" in text


@pytest.fixture
def inertia_context(
    browser: Browser, browser_context_args: dict, inertia_storage_state: str
) -> Iterator[BrowserContext]:
    ctx = browser.new_context(
        **browser_context_args,
        storage_state=Path(inertia_storage_state),
        viewport={"width": 1280, "height": 720},
    )
    yield ctx
    ctx.close()


@pytest.fixture
def page(inertia_context: BrowserContext, request: pytest.FixtureRequest) -> Iterator[Page]:
    """Signed-in page that fails the test on any console error or page error."""
    pg = inertia_context.new_page()
    allow_resource = request.node.get_closest_marker("allow_resource_errors") is not None
    problems: list[str] = []
    pg.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    pg.on(
        "console",
        lambda m: (
            m.type == "error"
            and not _noise(m.text, allow_resource)
            and problems.append(f"console.error: {m.text}")
        ),
    )
    yield pg
    pg.close()
    assert not problems, "browser errors:\n" + "\n".join(problems)


@pytest.fixture(autouse=True)
def reset_probes(inertia_context: BrowserContext) -> None:
    assert inertia_context.request.post(f"{PREFIX}/_probes/reset").ok


@pytest.fixture
def probes(inertia_context: BrowserContext) -> Callable[[], dict[str, int]]:
    def read() -> dict[str, int]:
        return json.loads(inertia_context.request.get(f"{PREFIX}/_probes").text())

    return read
