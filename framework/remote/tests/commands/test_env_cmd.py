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
    assert "Traceback" not in result.output and "permission denied" in result.output
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


@pytest.mark.parametrize(
    "url",
    [
        "https://a.com\n/x",
        "https://exa mple.com",
        "https://a.com\\b.com",
        "https://a.com/\x1b]0;x\x07",
    ],
)
def test_env_add_rejects_whitespace_control_and_backslash_urls(make_cli, url):
    result = CliRunner().invoke(make_cli(), ["env", "add", "bad", "--url", url])
    assert result.exit_code == 1 and "\x1b" not in result.output


def test_env_list_and_show_sanitise_hand_edited_values(make_cli, xdg_config):
    (xdg_config / "config.toml").write_text(
        '[env.evil]\nurl = "https://a.com/\\u001b]0;PWN\\u0007x"\ntenant = "t"\n'
    )
    cli = make_cli()
    for args in (["env", "list"], ["env", "show", "evil"]):
        out = CliRunner().invoke(cli, args).output
        assert "\x1b" not in out and "\x07" not in out


@pytest.mark.parametrize("tenant", ["a b", "a\nb", "x" * 200])
def test_tenant_is_validated(make_cli, tenant):
    runner = CliRunner()
    assert (
        runner.invoke(
            make_cli(), ["env", "add", "t", "--url", "https://x.example", "--tenant", tenant]
        ).exit_code
        == 1
    )
    assert runner.invoke(make_cli(), ["--tenant", tenant, "whoami"]).exit_code == 1


@pytest.mark.parametrize("name", ["-", "--x", "a" * 41])
def test_env_names_are_bounded_and_start_alphanumeric(make_cli, name):
    result = CliRunner().invoke(make_cli(), ["env", "add", name, "--url", "https://x.example"])
    assert result.exit_code != 0


def test_origin_is_normalised(make_cli):
    from simple_module_remote.config.environments import Environment

    assert Environment("a", "https://EXAMPLE.com:443/x").origin == "https://example.com"
    assert Environment("a", "http://localhost:8000").origin == "http://localhost:8000"


def test_no_subcommand_shows_help_not_an_error(make_cli):
    for args in ([], ["env"], ["users"]):
        result = CliRunner().invoke(make_cli(), args)
        assert "Usage:" in result.output and "Error" not in result.output
        assert result.exit_code in (0, 2)


def test_see_help_suffix_only_on_click_usage_errors(make_cli):
    cli = make_cli()
    bad_option = CliRunner().invoke(cli, ["env", "add", "x", "--nope"])
    assert "(see --help)" in bad_option.output
    refusal = CliRunner().invoke(cli, ["env", "add", "fresh"])  # our own refusal
    assert "--url is required" in refusal.output and "(see --help)" not in refusal.output
    protected = CliRunner().invoke(cli, ["users", "list-users", "--page", "x"])
    assert "(see --help)" in protected.output


def test_version_flag(make_cli):
    result = CliRunner().invoke(make_cli(), ["--version"])
    assert result.exit_code == 0 and result.output.startswith("smdev 1.2 (simple_module_remote ")


def test_remove_says_reset_for_a_project_default_and_warns_about_current(make_cli, tmp_path):
    defaults = tmp_path / "defaults.toml"
    defaults.write_text('[env.local]\nurl = "http://localhost:8000"\n')
    cli = make_cli()
    cli.context_settings["obj"].defaults_path = defaults
    runner = CliRunner()
    runner.invoke(cli, ["env", "add", "local", "--url", "http://127.0.0.1:8247"])
    runner.invoke(cli, ["env", "use", "local"])
    result = runner.invoke(cli, ["env", "remove", "local"])
    assert "reset environment local to the project default" in result.output
    assert "no environment is selected now" in result.output
