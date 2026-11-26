import httpx


def test_tenant_flag_is_ignored_with_a_note_on_a_single_tenant_server(make_cli, logged_in, who):
    single = who(tenant_id="default")
    cli = make_cli(lambda r: httpx.Response(200, json=single))
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["--tenant", "foo", "login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 0, result.output
    assert "single-tenant server; --tenant foo is ignored" in result.output
    again = runner.invoke(cli, ["--tenant", "foo", "whoami"])  # the pin check does not refuse it
    assert again.exit_code == 0, again.output
    doctor = runner.invoke(cli, ["--tenant", "foo", "doctor"]).output
    assert "single-tenant server" in doctor and "FAIL" not in doctor


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


def test_banner_names_the_tenant_by_slug_however_it_was_typed(make_cli, logged_in, who):
    cli = make_cli(lambda r: httpx.Response(200, json=who(tenant_slug="acme")))
    runner = logged_in(cli, login=False)
    runner.invoke(cli, ["--tenant", "t-1", "login", "--token-stdin"], input="tok\n")
    result = runner.invoke(
        cli, ["--tenant", "t-1", "api", "POST", "/api/users/x", "--json", "{}", "--yes"]
    )
    assert "[dev/acme]" in result.output and "[dev/t-1]" not in result.output
