"""A live schema is server-supplied: it must never weaken safety or reach the terminal raw."""

import gzip
import json

import httpx
import pytest
from simple_module_remote.commands import runtime, schema_cmd, schema_fetch, schema_source
from simple_module_remote.config.paths import cache_dir

OPENAPI = "/api/_meta/openapi"
TOKEN = "smpat_trust_boundary_secret_9876543210"
WHOAMI = {"id": "u", "email": "a@b", "auth_kind": "pat", "scopes": None, "tenant_id": None,
          "roles": []}  # fmt: skip
ESC = "\x1b[31m"
BODY = json.dumps({"email": "a@b"})


def test_live_safe_mark_does_not_waive_protected_confirmation(live, run_live):
    live["paths"]["/api/users"]["post"]["x-cli-safe"] = True
    synced, result, seen, runner, cli = run_live(
        live, "users", "create-user", "--json", BODY, protected=True
    )
    assert synced.exit_code == 0, synced.output
    assert result.exit_code == 1 and "protected" in result.output, result.output
    assert not [r for r in seen if r.method == "POST"]
    raw = runner.invoke(cli, ["api", "POST", "/api/users", "--json", BODY])
    assert raw.exit_code == 1 and "protected" in raw.output
    assert not [r for r in seen if r.method == "POST"]


def test_live_confirm_mark_adds_a_confirmation(live, run_live):
    live["paths"]["/api/ping"]["get"]["x-cli-confirm"] = True
    _, result, seen, runner, cli = run_live(live, "host", "ping", protected=True)
    assert result.exit_code == 1 and "protected" in result.output, result.output
    raw = runner.invoke(cli, ["api", "GET", "/api/ping"])
    assert raw.exit_code == 1 and "protected" in raw.output
    assert not [r for r in seen if r.url.path == "/api/ping"]


def test_invalid_cli_name_is_refused_at_sync(live, run_live):
    live["paths"]["/api/ping"]["get"]["x-cli-name"] = f"{ESC}evil"
    synced, *_ = run_live(live)
    assert synced.exit_code == 1 and "invalid x-cli-name" in synced.output
    assert "\x1b" not in synced.output
    assert not (cache_dir("smdev") / "dev" / "openapi.json").exists()


def test_server_text_is_sanitized_in_help_status_and_session_only(live, run_live):
    live["info"]["version"] = f"{ESC}9"
    live["paths"]["/api/ping"]["get"]["summary"] = f"{ESC}Ping"
    live["paths"][f"/api/odd{ESC}"] = {"get": {"operationId": f"odd{ESC}", "x-sm-token": False}}
    live["paths"]["/api/users"]["get"]["parameters"][0]["schema"]["enum"] = [f"{ESC}a", "b"]
    _, _, _, runner, cli = run_live(live)
    for args in (
        ["schema", "status"],
        ["host", "ping", "--help"],
        ["host", "--help"],
        ["api", "--session-only"],
        ["users", "list-users", "--help"],
    ):
        out = runner.invoke(cli, args).output
        assert "\x1b" not in out, (args, out)


@pytest.mark.parametrize(
    "placement",
    [
        lambda doc: doc["paths"]["/api/ping"]["get"].update({TOKEN: 1}),  # a key
        lambda doc: doc["info"].update(description=f"{TOKEN[:6]}\x1b{TOKEN[6:]}"),  # split
        lambda doc: doc["info"].update(description=f"{TOKEN[:6]}\x00{TOKEN[6:]}"),  # NUL
    ],
)
def test_token_reflected_anywhere_is_refused(live, run_live, placement):
    placement(live)
    synced, *_ = run_live(live)
    assert synced.exit_code == 1 and "credential" in synced.output, synced.output
    assert not (cache_dir("smdev") / "dev" / "openapi.json").exists()


def test_token_hidden_in_json_escapes_is_refused(live, run_live):
    escaped = "".join(f"\\u{ord(ch):04x}" for ch in TOKEN)
    body = json.dumps(live).replace('"title": "t"', f'"title": "{escaped}"')
    synced, *_ = run_live(live, response=httpx.Response(200, content=body.encode()))
    assert synced.exit_code == 1 and "credential" in synced.output, synced.output


def test_compressed_schema_is_refused_and_identity_requested(live, run_live):
    live["info"]["description"] = "x" * 100_000
    packed = gzip.compress(json.dumps(live).encode())
    reply = httpx.Response(200, content=packed, headers={"Content-Encoding": "gzip"})
    synced, _, seen, *_ = run_live(live, response=reply)
    assert synced.exit_code == 1 and "compressed" in synced.output
    assert [r for r in seen if r.url.path == OPENAPI][-1].headers["Accept-Encoding"] == "identity"


def test_fetch_budget_is_enforced_while_reading(live, run_live, monkeypatch):
    monkeypatch.setattr(schema_fetch, "MAX_SCHEMA_BYTES", 4096)
    live["info"]["description"] = "x" * 100_000
    body = json.dumps(live).encode()

    def chunks():
        yield from (body[i : i + 1000] for i in range(0, len(body), 1000))

    synced, *_ = run_live(live, response=httpx.Response(200, content=chunks()))
    assert synced.exit_code == 1 and "larger than 4096 bytes" in synced.output


def test_malformed_tree_is_a_safe_error_at_sync(live, run_live, monkeypatch):
    def boom(*a, **k):
        raise RecursionError

    monkeypatch.setattr(schema_fetch, "build_groups", boom)
    synced, *_ = run_live(live)
    assert synced.exit_code == 1 and "malformed (RecursionError)" in synced.output


def test_malformed_cache_falls_back_to_bundled_with_a_note(live, run_live, monkeypatch):
    _, _, _, runner, cli = run_live(live)
    real = schema_source.build_groups

    def boom(root, factory):
        if root.get("info", {}).get("version") == "9.9" and root is not cli.bundled.root:
            raise TypeError
        return real(root, factory)

    monkeypatch.setattr(schema_source, "build_groups", boom)
    result = runner.invoke(cli, ["schema", "status"])
    assert result.exit_code == 0 and "source:      bundled" in result.output
    assert "malformed (TypeError)" in result.output


def test_live_not_found_still_hints_at_a_refresh(live, run_live):
    _, result, *_ = run_live(live, "host", "ping")
    assert result.exit_code == 5
    assert "the server may have changed" in result.output and "schema sync" in result.output


def test_request_uses_the_env_resolved_before_parsing(live, run_live, monkeypatch):
    _, _, seen, runner, cli = run_live(live)

    def reread(*a, **k):
        raise AssertionError("config read again after the schema was chosen")

    monkeypatch.setattr(runtime, "load_config", reread)
    result = runner.invoke(cli, ["host", "ping"])
    assert "config read again" not in result.output and result.exit_code == 5
    assert seen[-1].url.host == "localhost"


def test_default_map_env_and_schema_are_honoured(live, run_live):
    live["paths"]["/api/reports"] = {"get": {"tags": ["Reports"], "operationId": "reports_list",
                                             "x-sm-token": True}}  # fmt: skip
    _, _, seen, runner, cli = run_live(live)
    runner.invoke(cli, ["env", "add", "other", "--url", "http://127.0.0.1:9"])
    runner.invoke(cli, ["env", "use", "other"])
    cli.context_settings["default_map"] = {"env": "dev"}
    result = runner.invoke(cli, ["reports", "list"])
    assert result.exit_code == 5, result.output  # live command, sent to dev
    assert seen[-1].url.path == "/api/reports" and seen[-1].url.host == "localhost"
    cli.context_settings["default_map"] = {"env": "dev", "schema_source": "bundled"}
    assert runner.invoke(cli, ["reports", "list"]).exit_code != 5


def test_not_modified_refresh_rechecks_the_fingerprint(live, run_live, monkeypatch):
    _, _, _, runner, cli = run_live(live)
    real = schema_cmd._cached_meta
    calls = []

    def flaky(store, env):
        meta = real(store, env)
        calls.append(meta)
        if len(calls) == 2 and meta is not None:
            return meta.__class__(meta.url, meta.origin, "0" * 64, meta.etag, meta.fetched_at)
        return meta

    monkeypatch.setattr(schema_cmd, "_cached_meta", flaky)
    not_modified = schema_fetch.Fetched(304, b"", None)
    monkeypatch.setattr(schema_cmd, "fetch_schema", lambda client, headers: not_modified)
    result = runner.invoke(cli, ["schema", "sync"])
    assert result.exit_code == 1 and "changed during the sync" in result.output, result.output
