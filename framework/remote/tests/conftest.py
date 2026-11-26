import copy
import json
from pathlib import Path

import httpx
import keyring.backends.fail
import pytest
from click.testing import CliRunner
from simple_module_remote import build_cli

MINI = Path(__file__).parent / "generate" / "fixtures" / "mini_openapi.json"
CLI = "smdev"
WHOAMI = {
    "id": "u1",
    "email": "ada@example.com",
    "name": "Ada",
    "auth_kind": "token",
    "scopes": ["users:read"],
    "tenant_id": "t-1",
    "roles": [],
}
WHOAMI_OP = {
    "get": {
        "tags": ["Meta"],
        "operationId": "meta_whoami",
        "x-sm-token": True,
        "x-cli-safe": True,
    }
}


class FakeKeyring:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.data[(service, username)]


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    for var in ("SMDEV_ENV", "SMDEV_TOKEN", "SMDEV_YES"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def mini_path() -> Path:
    return MINI


@pytest.fixture
def clean_schema(tmp_path) -> Path:
    """The mini schema without the deliberately colliding groups, plus whoami."""
    data = copy.deepcopy(json.loads(MINI.read_text()))
    for path in ("/api/dup/a", "/api/dup/b", "/api/env"):
        del data["paths"][path]
    data["paths"]["/api/_meta/whoami"] = WHOAMI_OP
    data["info"] = {"title": "t", "version": "9.9"}
    target = tmp_path / "openapi.json"
    target.write_text(json.dumps(data))
    return target


@pytest.fixture
def keyring_store() -> FakeKeyring:
    return FakeKeyring()


@pytest.fixture
def make_cli(clean_schema, keyring_store):
    """Build the CLI over ``handler``; requests are recorded on ``cli.requests``."""

    def factory(handler=None, *, schema=None, backend=None):
        requests: list[httpx.Request] = []

        def wrapped(req: httpx.Request) -> httpx.Response:
            requests.append(req)
            if handler is None:
                return httpx.Response(200, json=WHOAMI)
            return handler(req)

        cli = build_cli(
            CLI,
            schema or clean_schema,
            version="1.2",
            transport=httpx.MockTransport(wrapped),
            keyring_backend=backend or keyring_store,
        )
        cli.requests = requests
        return cli

    return factory


@pytest.fixture
def fail_keyring():
    return keyring.backends.fail.Keyring()


@pytest.fixture
def logged_in():
    """``logged_in(cli, ...)``: a runner with env ``dev`` added and selected, then logged in."""

    def factory(cli, *, protected=False, extra=(), login=True) -> CliRunner:
        runner = CliRunner()
        args = ["env", "add", "dev", "--url", "http://localhost:8000", *extra]
        runner.invoke(cli, args + (["--protected"] if protected else []))
        runner.invoke(cli, ["env", "use", "dev"])
        if login:
            runner.invoke(cli, ["login", "--token-stdin"], input="tok\n")
        return runner

    return factory
