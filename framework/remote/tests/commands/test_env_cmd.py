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
