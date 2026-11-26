import os

import pytest
from click.testing import CliRunner


def test_env_add_use_list(make_cli):
    cli, runner = make_cli(), CliRunner()
    out = runner.invoke(cli, ["env", "add", "prod", "--url", "https://app.example", "--protected"])
    assert out.exit_code == 0, out.output
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000", "--tenant", "acme"])
    assert runner.invoke(cli, ["env", "use", "prod"]).exit_code == 0
    listing = runner.invoke(cli, ["env", "list"]).output
    assert "* prod  https://app.example  [PROTECTED]" in listing
    assert "  dev  http://localhost:8000  [tenant=acme]" in listing
    shown = runner.invoke(cli, ["env", "show"]).output
    assert "prod" in shown and "protected: yes" in shown
    assert runner.invoke(cli, ["env", "remove", "prod"]).exit_code == 0
    assert "prod" not in runner.invoke(cli, ["env", "list"]).output


def test_env_add_rejects_bad_input(make_cli):
    cli, runner = make_cli(), CliRunner()
    assert (
        runner.invoke(cli, ["env", "add", "Bad Name", "--url", "https://x.example"]).exit_code == 1
    )
    assert runner.invoke(cli, ["env", "add", "x", "--url", "http://remote.example"]).exit_code == 1
    assert runner.invoke(cli, ["env", "use", "nope"]).exit_code == 1


def test_env_add_keeps_protected_and_tenant_of_existing(make_cli, tmp_path):
    defaults = tmp_path / "defaults.toml"
    defaults.write_text(
        '[env.prod]\nurl = "https://app.example"\nprotected = true\ntenant = "acme"\n'
    )
    cli = make_cli()
    cli_state = cli.context_settings["obj"]
    cli_state.defaults_path = defaults
    runner = CliRunner()
    assert (
        runner.invoke(cli, ["env", "add", "prod", "--url", "https://other.example"]).exit_code == 0
    )
    shown = runner.invoke(cli, ["env", "show", "prod"]).output
    assert "protected: yes" in shown and "tenant:    acme" in shown
    assert (
        runner.invoke(
            cli, ["env", "add", "prod", "--url", "https://other.example", "--no-protected"]
        ).exit_code
        == 0
    )
    assert "protected: no" in runner.invoke(cli, ["env", "show", "prod"]).output
    assert "tenant:    acme" in runner.invoke(cli, ["env", "show", "prod"]).output


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_env_add_into_readonly_config_dir_is_clean(make_cli, tmp_path):
    config = tmp_path / "config" / "smdev"
    config.mkdir(parents=True)
    config.chmod(0o500)
    try:
        result = CliRunner().invoke(make_cli(), ["env", "add", "x", "--url", "https://x.example"])
    finally:
        config.chmod(0o700)
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output and "PermissionError" in result.output
    assert str(config) in result.output


def _login(runner, make_cli, *extra):
    runner.invoke(make_cli(), [*extra, "login", "--token-stdin"], input="tok\n")


def test_env_remove_deletes_every_stored_login(make_cli, keyring_store):
    cli, runner = make_cli(), CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "add", "devx", "--url", "http://localhost:8001"])
    runner.invoke(cli, ["env", "use", "dev"])
    _login(runner, make_cli)
    _login(runner, make_cli, "--tenant", "t-1")
    runner.invoke(cli, ["--env", "devx", "login", "--token-stdin"], input="tok\n")
    assert {k[1] for k in keyring_store.creds} == {"dev", "dev/t-1", "devx"}
    result = runner.invoke(cli, ["env", "remove", "dev"])
    assert result.exit_code == 0, result.output
    assert "removed stored login dev\n" in result.output
    assert "removed stored login dev/t-1" in result.output
    assert {k[1] for k in keyring_store.creds} == {"devx"}  # a prefix sibling is untouched


def test_env_remove_deletes_file_store_logins(make_cli, fail_keyring):
    cli, runner = make_cli(backend=fail_keyring), CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "use", "dev"])
    runner.invoke(cli, ["login", "--token-stdin"], input="tok\n")
    runner.invoke(cli, ["--tenant", "t-1", "login", "--token-stdin"], input="tok\n")
    result = runner.invoke(cli, ["env", "remove", "dev"])
    assert "removed stored login dev/t-1" in result.output
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    runner.invoke(cli, ["env", "use", "dev"])
    assert runner.invoke(cli, ["whoami"]).exit_code == 1  # no stored credentials remain


def test_env_add_without_url_updates_an_existing_env(make_cli):
    cli, runner = make_cli(), CliRunner()
    runner.invoke(cli, ["env", "add", "prod", "--url", "https://app.example", "--protected"])
    result = runner.invoke(cli, ["env", "add", "prod", "--no-protected"])
    assert result.exit_code == 0, result.output
    shown = runner.invoke(cli, ["env", "show", "prod"]).output
    assert "protected: no" in shown and "https://app.example" in shown
    assert "warning" not in result.output  # nothing that a login depends on changed


def test_env_add_without_url_for_new_env_needs_url(make_cli):
    result = CliRunner().invoke(make_cli(), ["env", "add", "fresh", "--protected"])
    assert result.exit_code == 1 and "--url is required" in result.output


def test_env_add_warns_when_url_or_tenant_change(make_cli):
    cli, runner = make_cli(), CliRunner()
    runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:8000"])
    moved = runner.invoke(cli, ["env", "add", "dev", "--url", "http://localhost:9000"])
    assert "stored login" in moved.output and "login" in moved.output
    retenant = runner.invoke(cli, ["env", "add", "dev", "--tenant", "acme"])
    assert "stored login" in retenant.output
