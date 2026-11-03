"""E2E tests for which framework paths answer anonymous requests.

The framework's public paths are matched exactly or by a ``/``-terminated
prefix: ``/health`` and ``/health/ready`` are probes, ``/api/docs`` is the
documentation page, but a module route that merely *starts* with one of
those words (``/healthcare``, ``/api/docsearch``) gets the normal sign-in
treatment. Pinned against the running app because the decision is spread
over the auth, maintenance and rate-limit middleware.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import APIRequestContext

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("path", ["/health", "/health/ready"])
def test_probe_paths_answer_anonymously(playwright, base_url: str, path: str) -> None:
    request: APIRequestContext = playwright.request.new_context(base_url=base_url)
    try:
        response = request.get(path, max_redirects=0)
        assert response.status == 200
        body = response.json()
        assert body["status"] in {"healthy", "degraded", "unhealthy"}
    finally:
        request.dispose()


@pytest.mark.parametrize("path", ["/healthcare/records", "/api/docsearch"])
def test_similarly_named_paths_are_not_public(playwright, base_url: str, path: str) -> None:
    """Anything but a 200: a sign-in redirect, 401, or 404 for an unknown route."""
    request: APIRequestContext = playwright.request.new_context(base_url=base_url)
    try:
        response = request.get(path, max_redirects=0)
        assert response.status != 200
    finally:
        request.dispose()
