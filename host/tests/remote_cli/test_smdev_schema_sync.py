"""End-to-end: ``smdev schema sync`` against the real dev host's ``/api/_meta/openapi``."""

from __future__ import annotations

from simple_module_remote.config.paths import cache_dir
from smdev_cli import CLI_NAME

OPENAPI_PATH = "/api/_meta/openapi"


async def test_schema_sync_then_live_source(smdev, make_actor):
    admin = await make_actor()
    await smdev.add_env()
    token = await smdev.token_for(admin)
    assert (await smdev.login(token)).exit_code == 0

    first = await smdev.run("--env", "local", "schema", "sync")
    assert first.exit_code == 0, first.output
    assert "updated" in first.output
    cached = cache_dir(CLI_NAME) / "local"
    for name in ("openapi.json", "meta.json"):
        assert token.encode() not in (cached / name).read_bytes()

    status = await smdev.run("--env", "local", "schema", "status")
    assert "source:      live" in status.output, status.output

    again = await smdev.run("--env", "local", "schema", "sync")
    assert again.exit_code == 0 and "unchanged" in again.output, again.output
    conditional = [r for r in smdev.transport.requests if r.url.path == OPENAPI_PATH][-1]
    assert conditional.headers.get("If-None-Match")

    listed = await smdev.run(
        "--env", "local", "--schema", "live", "users", "admin-list-users", "-o", "json"
    )
    assert listed.exit_code == 0, listed.output
    assert admin.email in listed.output
