from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from simple_module_inertia.protocol.response import (
    fragment_redirect,
    json_response,
    location,
    redirect,
    version_conflict,
)


def test_legacy_response_import_warns_and_aliases_protocol_response() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            dedent("""\
                import importlib
                import sys
                import warnings

                for _ in range(2):
                    sys.modules.pop("simple_module_inertia.response", None)
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always", DeprecationWarning)
                        legacy = importlib.import_module("simple_module_inertia.response")
                    assert len(caught) == 1, caught
                    assert caught[0].category is DeprecationWarning
                    assert str(caught[0].message) == (
                        "simple_module_inertia.response is deprecated and will be removed in "
                        "0.0.55; use simple_module_inertia.protocol.response instead"
                    )
                    canonical = importlib.import_module("simple_module_inertia.protocol.response")
                    assert legacy is canonical
                    assert sys.modules["simple_module_inertia.response"] is canonical
                    assert legacy.InertiaResponse is importlib.import_module(
                        "simple_module_inertia"
                    ).InertiaResponse
                    assert "simple_module_core" not in sys.modules
                """),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_json_response_carries_the_inertia_headers_and_encoded_page() -> None:
    resp = json_response({"component": "C", "props": {"p": Path("/x")}, "url": "/", "version": "v"})
    assert resp.status_code == 200
    assert resp.headers["X-Inertia"] == "true"
    assert resp.headers["Vary"] == "Accept"
    assert json.loads(resp.body)["props"]["p"] == "/x"


def test_version_conflict_is_a_409_with_location_and_version() -> None:
    resp = version_conflict("http://h/admin/", "v2")
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Location"] == "http://h/admin/"
    assert resp.headers["X-Inertia-Version"] == "v2"


@pytest.mark.parametrize(
    ("method", "status"),
    [("POST", 303), ("PUT", 303), ("PATCH", 303), ("DELETE", 303), ("GET", 307)],
)
def test_redirect_uses_303_after_a_mutation(method: str, status: int) -> None:
    resp = redirect("/next", method=method)
    assert resp.status_code == status
    assert resp.headers["location"] == "/next"


def test_location_is_an_external_redirect() -> None:
    resp = location("https://elsewhere.example")
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Location"] == "https://elsewhere.example"


def test_fragment_redirect_keeps_the_fragment_client_side() -> None:
    resp = fragment_redirect("/docs#install")
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Redirect"] == "/docs#install"
