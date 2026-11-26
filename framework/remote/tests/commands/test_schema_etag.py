"""A non-ASCII ETag must never be stored or replayed as ``If-None-Match``."""

import json

import httpx
from simple_module_remote.config.paths import cache_dir

OPENAPI = "/api/_meta/openapi"
TOKEN = "smpat_etag_schema_secret_0123456789"
ODD = "W/étag"


def _server(doc, etag_header, whoami):
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == OPENAPI:
            return httpx.Response(200, json=doc, headers={"ETag": etag_header})
        if req.url.path == "/api/_meta/whoami":
            return httpx.Response(200, json=whoami)
        return httpx.Response(404, json={"detail": "Not Found"})

    handler.seen = seen
    return handler


def test_non_ascii_cached_etag_is_not_replayed(make_cli, logged_in, clean_schema, who):
    doc = json.loads(clean_schema.read_text())
    server = _server(doc, 'W/"v1"', who())
    cli = make_cli(server)
    runner = logged_in(cli, login=False)
    runner.invoke(make_cli(), ["login", "--token-stdin"], input=f"{TOKEN}\n")
    assert runner.invoke(cli, ["schema", "sync"]).exit_code == 0
    meta_path = cache_dir("smdev") / "dev" / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["etag"] = ODD
    meta_path.write_text(json.dumps(meta))
    server.seen.clear()
    result = runner.invoke(cli, ["schema", "sync"])
    assert result.exit_code == 0, result.output
    sent = [r for r in server.seen if r.url.path == OPENAPI]
    assert sent and "If-None-Match" not in sent[0].headers


def test_304_without_a_validator_is_a_protocol_error(make_cli, logged_in, clean_schema, who):
    doc = json.loads(clean_schema.read_text())
    state = {"status": 200}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == OPENAPI:
            if state["status"] == 304:
                return httpx.Response(304)
            return httpx.Response(200, json=doc)  # no ETag: nothing to validate with
        if req.url.path == "/api/_meta/whoami":
            return httpx.Response(200, json=who())
        return httpx.Response(404, json={"detail": "Not Found"})

    cli = make_cli(handler)
    runner = logged_in(cli, login=False)
    runner.invoke(make_cli(), ["login", "--token-stdin"], input=f"{TOKEN}\n")
    assert runner.invoke(cli, ["schema", "sync"]).exit_code == 0
    meta_path = cache_dir("smdev") / "dev" / "meta.json"
    before = meta_path.read_text()
    state["status"] = 304
    result = runner.invoke(cli, ["schema", "sync"])
    assert result.exit_code != 0
    assert "304" in result.output
    assert meta_path.read_text() == before
