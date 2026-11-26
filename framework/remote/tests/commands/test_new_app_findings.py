"""Help, fingerprint and environment fixes found driving a new app's CLI (#1241)."""

import json

import httpx
from click.testing import CliRunner

WHOAMI = {"id": "u", "email": "a@b", "auth_kind": "pat", "scopes": None, "tenant_id": None,
          "roles": []}  # fmt: skip


def _fingerprint(output: str) -> str:
    line = next(ln for ln in output.splitlines() if ln.startswith("fingerprint:"))
    return line.split()[-1]


def test_help_lists_body_fields_and_marks_required(make_cli):
    result = CliRunner().invoke(make_cli(), ["users", "create-user", "--help"])
    assert result.exit_code == 0, result.output
    text = " ".join(result.output.split())
    assert "Body fields for --set (* required):" in text
    assert "email* (string)" in text and "address (object)" in text and "meta (object)" in text


def test_help_without_a_json_body_lists_no_fields(make_cli):
    result = CliRunner().invoke(make_cli(), ["file-storage", "upload", "--help"])
    assert result.exit_code == 0, result.output
    assert "Body fields" not in result.output


TOKEN = "smpat_fingerprint_secret_0123456789"


def test_identical_schema_has_one_fingerprint_however_serialised(make_cli, logged_in, clean_schema):
    doc = json.loads(clean_schema.read_text())
    reordered = json.dumps(dict(reversed(list(doc.items()))), indent=4)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/_meta/openapi":
            if req.headers.get("If-None-Match") == '"v1"':
                return httpx.Response(304)
            return httpx.Response(200, content=reordered.encode(), headers={"ETag": '"v1"'})
        return httpx.Response(200, json=WHOAMI)

    cli = make_cli(handler)
    runner = logged_in(cli, login=False)  # "tok" occurs in the schema text: use a real token
    runner.invoke(make_cli(), ["login", "--token-stdin"], input=f"{TOKEN}\n")
    bundled = _fingerprint(runner.invoke(cli, ["schema", "status"]).output)
    synced = runner.invoke(cli, ["schema", "sync"])
    assert synced.exit_code == 0, synced.output
    assert f"updated ({bundled})" in synced.output
    live = runner.invoke(cli, ["schema", "status"]).output
    assert "source:      live" in live and _fingerprint(live) == bundled
    again = runner.invoke(cli, ["schema", "sync"])
    assert f"unchanged ({bundled})" in again.output


def test_login_selects_its_environment_when_none_is_current(make_cli):
    runner = CliRunner()
    cli = make_cli()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    result = runner.invoke(cli, ["--env", "dev", "login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 0, result.output
    assert "current environment: dev" in result.output
    assert runner.invoke(cli, ["whoami"]).exit_code == 0


def test_login_keeps_an_existing_current_environment(make_cli):
    runner = CliRunner()
    cli = make_cli()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "add", "other", "--url", "http://127.0.0.1:9000"])
    runner.invoke(cli, ["env", "use", "other"])
    result = runner.invoke(cli, ["--env", "dev", "login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 0, result.output
    assert "current environment" not in result.output
    # whoami still targets the current environment, which has no login of its own
    assert "for 'other'" in runner.invoke(cli, ["whoami"]).output
