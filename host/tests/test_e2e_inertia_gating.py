"""The Inertia e2e fixture routes exist in development only and need a signed-in user."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from host.e2e_inertia import mount_if_development
from host.e2e_inertia.constants import ROUTE_PREFIX

_PATHS = ("/_probes", "/", "/partial", "/forms", "/redirects", "/history")


def _client(*, development: bool) -> TestClient:
    app = FastAPI()
    mounted = mount_if_development(app, SimpleNamespace(is_development=development))
    assert mounted is development
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", _PATHS)
def test_absent_outside_development(path: str) -> None:
    assert _client(development=False).get(f"{ROUTE_PREFIX}{path}").status_code == 404


@pytest.mark.parametrize("path", _PATHS)
def test_anonymous_request_is_refused_in_development(path: str) -> None:
    assert _client(development=True).get(f"{ROUTE_PREFIX}{path}").status_code == 401


def test_probe_reset_is_guarded_too() -> None:
    assert _client(development=True).post(f"{ROUTE_PREFIX}/_probes/reset").status_code == 401
