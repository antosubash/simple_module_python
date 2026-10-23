"""Choose JSON or HTML for framework error responses."""

from starlette.requests import Request

from simple_module_hosting._inertia_shared import _INERTIA_HEADER


def _explicit_accept_q(accept: str, media_type: str) -> float | None:
    """Quality the Accept header gives ``media_type`` by explicit listing, or
    ``None`` when the caller never named it at all.

    Only exact entries count (no ``*/*`` / ``type/*`` wildcards) — the
    negotiation below cares whether the caller *named* html or json, and at
    what preference, and separately whether they named it *at all* (``None``
    vs. an explicit ``q=0``). Malformed q-values fall back to 1.0 per RFC 9110.
    """
    for part in accept.split(","):
        media, _, params = part.partition(";")
        if media.strip().lower() != media_type:
            continue
        q = 1.0
        for param in params.split(";"):
            name, _, value = param.partition("=")
            if name.strip().lower() == "q":
                try:
                    q = float(value.strip())
                except ValueError:
                    q = 1.0
        return q
    return None


def _wants_json(request: Request) -> bool:
    """API callers get JSON error bodies; browser-shaped requests get the page.

    A request that explicitly accepts ``text/html`` is a browser navigation —
    and those reach ``/api/*`` too (OAuth login links, file-download hrefs) —
    so it always gets the rendered page, unless the caller *prefers* JSON via
    q-values (``application/json, text/html;q=0.5`` is an API client keeping
    an html fallback). So does an Inertia visit (``X-Inertia`` header),
    whatever its Accept — an Inertia client can only consume Inertia-protocol
    responses, never a bare JSON body. Otherwise ``/api/*``, the documented
    prefix for every module's JSON surface (``ModuleMeta.route_prefix``),
    gets JSON — a bare ``fetch()`` sends ``Accept: */*`` — as does an
    explicit ``Accept: application/json`` anywhere else.

    ``text/html;q=0`` rules html out *everywhere*, not just under ``/api/*``:
    once the caller has explicitly said they won't accept html, this never
    chooses the html page. The (already-moot) html fallback survives only
    when json wasn't mentioned either — there's nothing else to offer, so a
    view path keeps its pre-existing default and an ``/api/*`` path keeps
    getting JSON either way.
    """
    if request.headers.get(_INERTIA_HEADER):
        return False
    accept = request.headers.get("accept", "")
    html_q = _explicit_accept_q(accept, "text/html")
    json_q = _explicit_accept_q(accept, "application/json")
    if html_q is not None and html_q > 0 and html_q >= (json_q or 0.0):
        return False
    path = request.url.path
    is_api = path == "/api" or path.startswith("/api/")
    if html_q == 0:
        return is_api if json_q is None else True
    return is_api or bool(json_q)
