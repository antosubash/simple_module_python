"""One schema, one fingerprint, however it is serialised (#1241)."""

import json

import httpx
from simple_module_remote.commands.schema_cmd import schema_fingerprint

TOKEN = "smpat_fingerprint_secret_0123456789"


def _fingerprint(output: str) -> str:
    return next(ln for ln in output.splitlines() if ln.startswith("fingerprint:")).split()[-1]


def test_identical_schema_has_one_fingerprint(make_cli, logged_in, clean_schema, who):
    doc = json.loads(clean_schema.read_text())
    reordered = json.dumps(dict(reversed(list(doc.items()))), indent=4)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/_meta/openapi":
            if req.headers.get("If-None-Match") == '"v1"':
                return httpx.Response(304)
            return httpx.Response(200, content=reordered.encode(), headers={"ETag": '"v1"'})
        return httpx.Response(200, json=who(tenant_id=None))

    cli = make_cli(handler)
    runner = logged_in(cli, login=False)  # "tok" occurs in the schema text: use a real token
    runner.invoke(make_cli(), ["login", "--token-stdin"], input=f"{TOKEN}\n")
    bundled = _fingerprint(runner.invoke(cli, ["schema", "status"]).output)
    synced = runner.invoke(cli, ["schema", "sync"])
    assert synced.exit_code == 0, synced.output
    assert f"updated ({bundled})" in synced.output
    live = runner.invoke(cli, ["schema", "status"]).output
    assert "source:      live" in live and _fingerprint(live) == bundled
    assert f"unchanged ({bundled})" in runner.invoke(cli, ["schema", "sync"]).output


def test_a_lone_surrogate_does_not_break_the_fingerprint():
    assert len(schema_fingerprint({"info": {"description": "\ud800"}})) == 12
