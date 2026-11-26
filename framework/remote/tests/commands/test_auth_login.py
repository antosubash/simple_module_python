import io
import sys

import httpx


def test_login_stdin_line_is_capped(make_cli, logged_in):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", "--token-stdin"], input="a" * 10000 + "\n")
    assert result.exit_code == 1 and "longer than 4096" in result.output
    assert cli.requests == []


def test_login_prompt_needs_a_terminal(make_cli, logged_in, monkeypatch):
    cli = make_cli()
    runner = logged_in(cli, login=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO("tok\n"))
    result = runner.invoke(cli, ["login", "--token"])
    assert result.exit_code == 1 and "--token-stdin" in result.output


def test_login_404_blames_the_url_not_the_token(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(404, json={}))
    result = logged_in(cli, login=False).invoke(cli, ["login", "--token-stdin"], input="tok\n")
    assert result.exit_code == 5 and "check the URL" in result.output


def test_whoami_401_suggests_login(make_cli, logged_in):
    cli = make_cli(lambda r: httpx.Response(401, json={}))
    runner = logged_in(cli, login=False)
    runner.invoke(make_cli(), ["login", "--token-stdin"], input="tok\n")
    result = runner.invoke(cli, ["whoami"])
    assert result.exit_code == 4 and "login --token" in result.output
