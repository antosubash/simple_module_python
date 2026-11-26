import httpx
import pytest


def test_single_tenant_login_uses_the_plain_slot(make_cli, keyring_store, logged_in, who):
    single = who(tenant_id="default", tenant_slug=None)
    cli = make_cli(lambda r: httpx.Response(200, json=single))
    runner = logged_in(cli, login=False)
    login = runner.invoke(cli, ["--tenant", "foo", "login", "--token-stdin"], input="tok\n")
    assert "logged in to dev as" in login.output
    assert {k[1] for k in keyring_store.creds} == {"dev"}
    assert runner.invoke(cli, ["whoami"]).exit_code == 0
    assert runner.invoke(cli, ["--tenant", "foo", "whoami"]).exit_code == 0
    out = runner.invoke(cli, ["--tenant", "foo", "logout"])
    assert out.exit_code == 0 and "logged out of dev" in out.output
    assert keyring_store.creds == {}


def test_doctor_tenant_line_shows_slug_and_id(make_cli, logged_in, who):
    cli = make_cli(lambda r: httpx.Response(200, json=who(tenant_slug="acme")))
    runner = logged_in(cli, login=False)
    runner.invoke(cli, ["--tenant", "t-1", "login", "--token-stdin"], input="tok\n")
    out = runner.invoke(cli, ["--tenant", "t-1", "doctor"]).output
    assert "ok    tenant: token is pinned to acme (t-1)" in out


def test_banner_names_the_tenant_by_slug_however_it_was_typed(make_cli, logged_in, who):
    cli = make_cli(lambda r: httpx.Response(200, json=who(tenant_slug="acme")))
    runner = logged_in(cli, login=False)
    runner.invoke(cli, ["--tenant", "t-1", "login", "--token-stdin"], input="tok\n")
    result = runner.invoke(
        cli, ["--tenant", "t-1", "api", "POST", "/api/users/x", "--json", "{}", "--yes"]
    )
    assert "[dev/acme]" in result.output and "[dev/t-1]" not in result.output


def test_no_active_organisation_is_a_tenant_reason(make_cli, logged_in):
    cli = make_cli(
        lambda r: httpx.Response(403, json={"detail": "No active organisation for this request"})
    )
    runner = logged_in(cli)
    result = runner.invoke(cli, ["api", "GET", "/api/settings/current"])
    assert "the server needs a tenant" in result.output and "login" not in result.output


@pytest.mark.parametrize("flag", ["--body-file"])
def test_missing_body_file_names_file_and_reason(make_cli, logged_in, flag):
    cli = make_cli()
    runner = logged_in(cli)
    result = runner.invoke(cli, ["file-storage", "put-raw", flag, "/nonexistent/part.bin", "--yes"])
    assert "/nonexistent/part.bin" in result.output and "no such file or directory" in result.output
    assert "FileNotFoundError" not in result.output
