import json
import stat

import httpx
import pytest
from simple_module_remote.commands.schema_cmd import schema_fingerprint
from simple_module_remote.config.paths import cache_dir

OPENAPI = "/api/_meta/openapi"
WHOAMI = {"id": "u", "email": "a@b", "auth_kind": "pat", "scopes": None, "tenant_id": None,
          "roles": []}  # fmt: skip
TOKEN = "smpat_live_schema_secret_0123456789"
REPORTS_OP = {
    "get": {
        "tags": ["Reports"],
        "operationId": "reports_list_reports",
        "summary": "List reports",
        "x-sm-token": True,
        "x-cli-safe": True,
    }
}


@pytest.fixture
def live_doc(clean_schema):
    """The bundled test schema plus a route the bundled one does not have."""
    data = json.loads(clean_schema.read_text())
    data["paths"]["/api/reports"] = REPORTS_OP
    data["info"]["version"] = "10.0"
    return data


@pytest.fixture
def server(live_doc):
    """A handler serving whoami, the live schema (ETag ``W/"v1"``) and the reports route."""
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == OPENAPI:
            if req.headers.get("If-None-Match") == 'W/"v1"':
                return httpx.Response(304)
            return httpx.Response(200, json=live_doc, headers={"ETag": 'W/"v1"'})
        if req.url.path == "/api/reports":
            return httpx.Response(200, json=[{"id": 1}])
        if req.url.path == "/api/_meta/whoami":
            return httpx.Response(200, json=WHOAMI)
        return httpx.Response(404, json={"detail": "Not Found"})

    handler.seen = seen
    return handler


@pytest.fixture
def signed_in(make_cli, logged_in):
    """``signed_in(cli)``: env ``dev`` selected and logged in with :data:`TOKEN`."""

    def factory(cli):
        runner = logged_in(cli, login=False)
        runner.invoke(make_cli(), ["login", "--token-stdin"], input=f"{TOKEN}\n")
        return runner

    return factory


def _env_dir():
    return cache_dir("smdev") / "dev"


def test_sync_writes_a_private_cache_without_the_token(make_cli, signed_in, server):
    cli = make_cli(server)
    runner = signed_in(cli)
    result = runner.invoke(cli, ["schema", "sync"])
    assert result.exit_code == 0, result.output
    assert "updated" in result.output and TOKEN not in result.output
    assert stat.S_IMODE(_env_dir().stat().st_mode) == 0o700
    files = {p.name: p for p in _env_dir().iterdir()}
    assert set(files) == {"openapi.json", "meta.json", "sync.lock"}
    for path in files.values():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert TOKEN.encode() not in path.read_bytes()
    meta = json.loads(files["meta.json"].read_text())
    assert meta["url"] == "http://localhost:8000" and meta["etag"] == 'W/"v1"'
    sent = [r for r in server.seen if r.url.path == OPENAPI]
    assert sent[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert "If-None-Match" not in sent[0].headers


def test_live_cache_adds_routes_the_bundled_schema_lacks(make_cli, signed_in, server):
    cli = make_cli(server)
    runner = signed_in(cli)
    before = runner.invoke(cli, ["reports", "list-reports"])
    assert before.exit_code != 0  # not in the bundled schema
    runner.invoke(cli, ["schema", "sync"])
    after = runner.invoke(cli, ["reports", "list-reports"])
    assert after.exit_code == 0, after.output
    assert any(r.url.path == "/api/reports" for r in server.seen)
    assert runner.invoke(cli, ["raw", "reports", "list-reports"]).exit_code == 0
    status = runner.invoke(cli, ["schema", "status"]).output
    assert "source:      live" in status and "10.0" in status and "age:" in status
    pinned = runner.invoke(cli, ["--schema", "bundled", "reports", "list-reports"])
    assert pinned.exit_code != 0
    assert (
        "source:      bundled"
        in runner.invoke(cli, ["--schema=bundled", "schema", "status"]).output
    )


def test_not_modified_keeps_the_cache(make_cli, signed_in, server):
    cli = make_cli(server)
    runner = signed_in(cli)
    runner.invoke(cli, ["schema", "sync"])
    schema_before = (_env_dir() / "openapi.json").read_bytes()
    meta_path = _env_dir() / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["fetched_at"] = "2020-01-01T00:00:00+00:00"
    meta_path.write_text(json.dumps(meta))
    result = runner.invoke(cli, ["--env", "dev", "schema", "sync"])
    assert result.exit_code == 0 and "unchanged" in result.output, result.output
    assert server.seen[-1].headers["If-None-Match"] == 'W/"v1"'
    assert (_env_dir() / "openapi.json").read_bytes() == schema_before
    assert json.loads(meta_path.read_text())["fetched_at"] != "2020-01-01T00:00:00+00:00"


def test_url_change_falls_back_to_bundled(make_cli, signed_in, server):
    cli = make_cli(server)
    runner = signed_in(cli)
    runner.invoke(cli, ["schema", "sync"])
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://127.0.0.1:9000"])
    status = runner.invoke(cli, ["schema", "status"]).output
    assert "source:      bundled" in status
    assert "now points at http://127.0.0.1:9000" in status and "schema sync" in status
    refused = runner.invoke(cli, ["--schema", "live", "reports", "list-reports"])
    assert refused.exit_code == 1 and "schema sync" in refused.output


def test_schema_live_without_a_cache_is_a_usage_error(make_cli, signed_in, server):
    cli = make_cli(server)
    runner = signed_in(cli)
    result = runner.invoke(cli, ["--schema", "live", "users", "list-users", "--page", "1"])
    assert result.exit_code == 1
    assert "--schema live" in result.output and "smdev --env dev schema sync" in result.output
    assert not [r for r in server.seen if r.url.path.startswith("/api/users")]
    # Built-ins still run, so the cache can be created with the same flags.
    assert runner.invoke(cli, ["--schema", "live", "schema", "sync"]).exit_code == 0
    assert runner.invoke(cli, ["--schema", "live", "reports", "list-reports"]).exit_code == 0


def test_not_found_from_a_bundled_command_hints_at_sync(make_cli, signed_in, server):
    cli = make_cli(server)
    runner = signed_in(cli)
    result = runner.invoke(cli, ["users", "list-users", "--page", "1"])
    assert result.exit_code == 5
    assert "hint:" in result.output and "smdev --env dev schema sync" in result.output
    raw_api = runner.invoke(cli, ["api", "GET", "/api/nothing"])
    assert "schema sync" not in raw_api.output


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(403, json={"detail": "no"}), "host.openapi.read"),
        (httpx.Response(404, json={"detail": "Not Found"}), "no /api/_meta/openapi route"),
        (httpx.Response(200, json=["not", "openapi"]), "not an OpenAPI document"),
        (httpx.Response(200, json={"openapi": "3.1.0", "paths": {}, "x": TOKEN}), "credential"),
        (httpx.Response(302, headers={"Location": "/elsewhere"}), "HTTP 302"),
    ],
)
def test_sync_refuses_bad_answers_and_writes_nothing(make_cli, signed_in, response, expected):
    cli = make_cli(lambda req: response)
    runner = signed_in(cli)
    result = runner.invoke(cli, ["schema", "sync"])
    assert result.exit_code != 0 and expected in result.output, result.output
    assert not (_env_dir() / "openapi.json").exists()
    assert not (_env_dir() / "meta.json").exists()


def test_sync_env_option_selects_the_environment(make_cli, signed_in, server):
    cli = make_cli(server)
    runner = signed_in(cli)
    runner.invoke(cli, ["env", "add", "other", "--url", "http://localhost:9"])
    runner.invoke(cli, ["env", "use", "other"])
    result = runner.invoke(cli, ["schema", "sync", "--env", "dev"])
    assert result.exit_code == 0, result.output
    assert (_env_dir() / "openapi.json").exists()


def _fingerprint(output: str) -> str:
    return next(ln for ln in output.splitlines() if ln.startswith("fingerprint:")).split()[-1]


def test_identical_schema_has_one_fingerprint(make_cli, signed_in, clean_schema):
    """However a schema is serialised, bundled and live show one fingerprint (#1241)."""
    doc = json.loads(clean_schema.read_text())
    reordered = json.dumps(dict(reversed(list(doc.items()))), indent=4).encode()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == OPENAPI:
            if req.headers.get("If-None-Match") == 'W/"v1"':
                return httpx.Response(304)
            return httpx.Response(200, content=reordered, headers={"ETag": 'W/"v1"'})
        if req.url.path == "/api/_meta/whoami":
            return httpx.Response(200, json=WHOAMI)
        return httpx.Response(404, json={"detail": "Not Found"})

    cli = make_cli(handler)
    runner = signed_in(cli)
    bundled = _fingerprint(runner.invoke(cli, ["schema", "status"]).output)
    synced = runner.invoke(cli, ["schema", "sync"])
    assert synced.exit_code == 0, synced.output
    assert f"updated ({bundled})" in synced.output
    live = runner.invoke(cli, ["schema", "status"]).output
    assert "source:      live" in live and _fingerprint(live) == bundled
    assert f"unchanged ({bundled})" in runner.invoke(cli, ["schema", "sync"]).output


def test_a_lone_surrogate_does_not_break_the_fingerprint():
    assert len(schema_fingerprint({"info": {"description": "\ud800"}})) == 12
