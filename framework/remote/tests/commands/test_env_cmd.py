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
