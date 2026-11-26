import pytest
from click.testing import CliRunner
from simple_module_remote.config.credentials import (
    CredentialStore,
    StoredCredential,
    resolve_token,
)
from simple_module_remote.config.environments import Environment
from simple_module_remote.http.safety import normalize_url


@pytest.mark.parametrize(
    "url", ["http://@127.0.0.1:8291", "https://@a.example", "https://:@a.example"]
)
def test_empty_userinfo_is_refused(make_cli, url):
    result = CliRunner().invoke(make_cli(), ["env", "add", "bad", "--url", url])
    assert result.exit_code == 1 and "credentials" in result.output


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("HTTPS://EXAMPLE.com:443/", "https://example.com"),
        ("http://Localhost:80/App/", "http://localhost/App"),
        ("https://example.com:8443/base/", "https://example.com:8443/base"),
        ("http://[::1]:8000", "http://[::1]:8000"),
    ],
)
def test_env_add_stores_the_canonical_url(make_cli, raw, stored):
    assert normalize_url(raw) == stored
    if not raw.startswith(("http://Localhost", "HTTPS")):
        return
    cli = make_cli()
    runner = CliRunner()
    url = raw.replace("HTTPS", "https")
    runner.invoke(cli, ["env", "add", "n", "--url", url])
    assert stored in runner.invoke(cli, ["env", "show", "n"]).output


def test_credentials_stored_before_normalisation_still_match(keyring_store):
    store = CredentialStore("smdev", backend=keyring_store)
    store.put("dev", StoredCredential("tok", "https://EXAMPLE.com:443"))
    env = Environment("dev", "https://example.com")
    assert resolve_token(store, env, None, {}, "smdev", explicit=False) == "tok"
