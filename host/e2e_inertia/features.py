"""In-memory Inertia protocol demonstrations (props, once, scroll, history)."""

import asyncio
from time import time
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_inertia import always, deep_merge, defer, merge, once, optional, prepend, scroll
from starlette.responses import RedirectResponse

from host.e2e_inertia import constants as c
from host.e2e_inertia.probes import count, counters, loader

router = APIRouter()


def once_props():
    return {
        "cached": once(loader("cached")),
        "expiring": once(
            loader("expiring"),
            key=c.ONCE_EXPIRING_KEY,
            expires_at=int(time() * 1000) + c.ONCE_EXPIRY_MS,
        ),
    }


@router.get("/")
async def index(inertia: InertiaDep):
    # The client carries once values across components that declare the same cache keys.
    return await inertia.render(
        c.PAGE_INDEX, {name: optional(prop) for name, prop in once_props().items()}
    )


@router.get("/_probes")
async def probes():
    return counters.copy()


@router.post("/_probes/reset")
async def reset_probes():
    counters.clear()
    return {}


@router.get("/partial")
async def partial(inertia: InertiaDep):
    return await inertia.render(
        c.PAGE_PARTIAL,
        {
            "stamp": always(loader("stamp")),
            "a": optional(loader("a")),
            "b": loader("b"),
            "nested": {"x": loader("nested.x"), "y": loader("nested.y")},
        },
    )


async def load_slow():
    call = count("slow")
    await asyncio.sleep(0.3)
    return call


def load_fragile():
    count("fragile")
    raise RuntimeError("Intentional rescued e2e loader failure")


@router.get("/deferred")
async def deferred(inertia: InertiaDep):
    return await inertia.render(
        c.PAGE_DEFERRED,
        {
            "fast": defer(loader("fast")),
            "slow": defer(load_slow, group="slow"),
            "fragile": defer(load_fragile, rescue=True),
        },
    )


@router.get("/merge")
async def merging(inertia: InertiaDep, page: Annotated[int, Query(ge=1, le=100)] = 1):
    start = (page - 1) * 3 + 1
    return await inertia.render(
        c.PAGE_MERGE,
        {
            "page": page,
            "items": merge(loader("items", list(range(start, start + 3)))),
            "prepended": prepend(loader("prepended", list(range(-start - 2, -start + 1)))),
            "tree": deep_merge(loader("tree", {"pages": {str(page): page}, "latest": page})),
            "matched": merge(
                loader(
                    "matched",
                    [
                        {"id": 1, "revision": page},
                        {"id": page + 1, "revision": page},
                    ],
                ),
                match_on="id",
            ),
        },
    )


@router.get("/once")
async def cached(inertia: InertiaDep):
    return await inertia.render(c.PAGE_ONCE, once_props())


@router.get("/scroll")
async def scrolling(
    inertia: InertiaDep,
    page: Annotated[int, Query(ge=1, le=10)] = 1,
    filter: Literal["all", "even"] = "all",
):
    ids = [number for number in range(1, 101) if filter == "all" or number % 2 == 0]
    last_page = (len(ids) + 9) // 10
    # Query validation bounds the public page number; a narrower filter can end earlier.
    posts = [{"id": number} for number in ids[(page - 1) * 10 : page * 10]]
    return await inertia.render(
        c.PAGE_SCROLL,
        {
            "posts": scroll(
                loader("posts", {"data": posts}),
                page_name="page",
                current_page=page,
                previous_page=page - 1 if page > 1 else None,
                next_page=page + 1 if page < last_page else None,
            ),
            "filter": filter,
        },
    )


@router.get("/visible")
async def visible(inertia: InertiaDep):
    return await inertia.render(
        c.PAGE_VISIBLE,
        {
            "below": optional(loader("below")),
            "tick": always(loader("tick")),
        },
    )


@router.get("/history/moved")
async def history_moved():
    # The visit's URL changes on the redirect, so only preserveFragment keeps its #hash.
    return RedirectResponse(f"{c.ROUTE_PREFIX}/history/fragment", status_code=302)


@router.get("/history/moved-plain")
async def history_moved_plain():
    return RedirectResponse(f"{c.ROUTE_PREFIX}/history/plain", status_code=302)


@router.get("/history")
@router.get("/history/{mode}")
async def history(
    inertia: InertiaDep, mode: Literal["encrypt", "clear", "fragment", "plain"] = "encrypt"
):
    if mode == "encrypt":
        inertia.encrypt_history()
    elif mode == "clear":
        inertia.clear_history()
    elif mode == "fragment":
        inertia.preserve_fragment()
    return await inertia.render(c.PAGE_HISTORY, {"mode": mode})
