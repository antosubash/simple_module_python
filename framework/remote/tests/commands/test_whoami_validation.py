import httpx
import pytest

WHO = {
    "id": "u",
    "email": "a@b",
    "auth_kind": "pat",
    "scopes": None,
    "tenant_id": "t-1",
    "tenant_slug": "acme",
    "roles": [],
}


@pytest.mark.parametrize(
    "bad",
    [
        {"tenant_slug": "a b"},
        {"tenant_slug": "a\nb"},
        {"tenant_slug": "x" * 200},
        {"tenant_slug": "slug-tok-slug"},  # reflects the token ("tok")
        {"tenant_id": "tok"},
        {"tenant_slug": 5},
    ],
)
def test_unsafe_tenant_identity_is_refused_and_never_stored(
    make_cli, logged_in, keyring_store, bad
):
    cli = make_cli(lambda r: httpx.Response(200, json={**WHO, **bad}))
    runner = logged_in(cli, login=False)
    result = runner.invoke(cli, ["login", "--token-stdin"], input="tok\n")
    assert result.exit_code != 0 and "identity document" in result.output
    assert keyring_store.creds == {}
    assert "slug-tok" not in result.output
