"""Strict (422) and lenient (clamp) page-param dependencies."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from simple_module_db import PageParams
from simple_module_hosting.pagination import lenient_page_params, page_params

app = FastAPI()


@app.get("/strict")
def strict(p: PageParams = Depends(page_params(50))) -> dict[str, int]:
    return {"page": p.page, "per_page": p.per_page, "offset": p.offset}


@app.get("/lenient")
def lenient(p: PageParams = Depends(lenient_page_params(20))) -> dict[str, int]:
    return {"page": p.page, "per_page": p.per_page, "offset": p.offset}


client = TestClient(app)


def test_strict_defaults_and_factory_page_size():
    assert client.get("/strict").json() == {"page": 1, "per_page": 50, "offset": 0}


def test_strict_rejects_out_of_range():
    for q in ("page=0", "page=-1", "per_page=0", "per_page=201", "page=abc"):
        assert client.get(f"/strict?{q}").status_code == 422, q


def test_lenient_clamps_instead_of_rejecting():
    assert client.get("/lenient?page=-4&per_page=9999").json() == {
        "page": 1,
        "per_page": 200,
        "offset": 0,
    }
    assert client.get("/lenient?page=banana").json()["page"] == 1
    assert client.get("/lenient").json()["per_page"] == 20


def test_strict_rejects_page_above_max():
    assert client.get("/strict?page=1000001").status_code == 422
    assert client.get("/strict?page=1000000").json()["page"] == 1_000_000


def test_lenient_clamps_page_to_max():
    assert client.get("/lenient?page=99999999999").json()["page"] == 1_000_000
