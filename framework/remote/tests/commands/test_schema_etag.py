"""A non-ASCII ETag must never be stored or replayed as ``If-None-Match``."""

import json

import httpx
from simple_module_remote.config.paths import cache_dir

OPENAPI = "/api/_meta/openapi"
TOKEN = "smpat_etag_schema_secret_0123456789"
WHOAMI = {"id": "u", "email": "a@b", "auth_kind": "pat", "scopes": None, "tenant_id": None,
          "roles": []}  # fmt: skip
ODD = "W/étag"


def _server(doc, etag_header):
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == OPENAPI:
            return httpx.Response(200, json=doc, headers={"ETag": etag_header})
        if req.url.path == "/api/_meta/whoami":
            return httpx.Response(200, json=WHOAMI)
        return httpx.Response(404, json={"detail": "Not Found"})

    handler.seen = seen
    return handler


def test_non_ascii_cached_etag_is_not_replayed(make_cli, logged_in, clean_schema):
    doc = json.loads(clean_schema.read_text())
    server = _server(doc, 'W/"v1"')
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
