"""Smoke test: LacoWiki module pages render via Inertia."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/lacowiki/",
        "/lacowiki/datasets",
        "/lacowiki/legends",
        "/lacowiki/sampling",
        "/lacowiki/validation",
        "/lacowiki/reports",
        "/lacowiki/account",
    ],
)
async def test_lacowiki_pages_render(authenticated_client, path: str) -> None:
    """Each page returns 200 (HTML or Inertia JSON, depending on Accept)."""
    response = await authenticated_client.get(path)
    assert response.status_code == 200
