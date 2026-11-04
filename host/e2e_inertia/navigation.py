"""Redirect normalization, history targets and hosting error demonstrations."""

from html import escape

from fastapi import APIRouter, Request
from simple_module_hosting.inertia_deps import InertiaDep
from starlette.responses import HTMLResponse, RedirectResponse, Response

from host.e2e_inertia.constants import PAGE_REDIRECTS, ROUTE_PREFIX

router = APIRouter()

_REDIRECTS_URL = f"{ROUTE_PREFIX}/redirects"
_EXTERNAL_LANDED = "External HTML destination"


@router.get("/redirects")
async def redirects(inertia: InertiaDep, done: str = ""):
    return await inertia.render(PAGE_REDIRECTS, {"done": done})


@router.api_route("/redirects/mutate", methods=["PUT", "PATCH", "DELETE"])
async def mutate(request: Request):
    return RedirectResponse(f"{_REDIRECTS_URL}?done={request.method.lower()}", status_code=302)


@router.post("/redirects/empty")
async def empty():
    return Response(status_code=200)


@router.post("/redirects/back")
async def back(inertia: InertiaDep):
    return inertia.back()


@router.get("/redirects/fragment")
async def fragment():
    return RedirectResponse(f"{_REDIRECTS_URL}#section-2", status_code=302)


@router.get("/redirects/external")
async def external(inertia: InertiaDep):
    return inertia.location(f"{ROUTE_PREFIX}/_external")


@router.get("/_external")
async def external_target():
    return HTMLResponse(
        '<!doctype html><html><body><h1 data-testid="e2e-external">'
        + escape(_EXTERNAL_LANDED)
        + "</h1></body></html>"
    )
