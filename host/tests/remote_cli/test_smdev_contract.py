"""End-to-end: the real ``smdev`` CLI against the real in-process dev host."""

from __future__ import annotations

import json

from simple_module_remote.generate.operations import parse_operations
from simple_module_remote.schema.loader import load_schema
from smdev_cli import SCHEMA_PATH

LIST_USERS = ("users", "admin-list-users")
UPDATE_USER = ("users", "admin-update-user")


def _items(output: str) -> list[dict]:
    data = json.loads(output)
    return data["items"] if isinstance(data, dict) else data


async def _ready(smdev, make_actor):
    admin = await make_actor()
    await smdev.add_env()
    login = await smdev.login(await smdev.token_for(admin))
    assert login.exit_code == 0, login.output
    smdev.transport.requests.clear()
    return admin


async def test_login_token_stdin_then_whoami(smdev, make_actor):
    admin = await make_actor()
    await smdev.add_env()
    login = await smdev.login(await smdev.token_for(admin))
    assert login.exit_code == 0, login.output
    assert admin.email in login.output
    who = await smdev.run("--env", "local", "whoami")
    assert who.exit_code == 0, who.output
    assert f"user:   {admin.email}" in who.output
    assert "auth:   pat" in who.output
    assert f"({admin.tenant_id})" in who.output  # "slug (id)"


async def test_generated_list_users_json(smdev, make_actor):
    admin = await _ready(smdev, make_actor)
    result = await smdev.run("--env", "local", *LIST_USERS, "-o", "json")
    assert result.exit_code == 0, result.output
    assert admin.email in {row["email"] for row in _items(result.output)}


async def test_generated_update_user_set(smdev, make_actor, make_user):
    await _ready(smdev, make_actor)
    user_id, email = await make_user()
    result = await smdev.run(
        "--env",
        "local",
        *UPDATE_USER,
        user_id,
        "--set",
        f"email={email}",
        "--set",
        "full_name=Renamed",
        "-o",
        "json",
    )
    assert result.exit_code == 0, result.output
    listed = await smdev.run("--env", "local", *LIST_USERS, "-o", "json")
    row = next(r for r in _items(listed.output) if r["id"] == user_id)
    assert row["full_name"] == "Renamed"


async def test_dry_run_sends_nothing(smdev, make_actor, make_user):
    await _ready(smdev, make_actor)
    user_id, email = await make_user()
    result = await smdev.run(
        "--env",
        "local",
        *UPDATE_USER,
        user_id,
        "--set",
        f"email={email}",
        "--set",
        "full_name=Nope",
        "--dry-run",
    )
    assert result.exit_code == 0, result.output
    assert smdev.transport.requests == []
    listed = await smdev.run("--env", "local", *LIST_USERS, "-o", "json")
    row = next(r for r in _items(listed.output) if r["id"] == user_id)
    assert row["full_name"] != "Nope"


async def test_session_only_route_absent(smdev):
    ops = parse_operations(load_schema(SCHEMA_PATH))
    hidden = [op for op in ops if not op.token_capable]
    assert hidden
    for op in hidden[:20]:
        result = await smdev.run("raw", op.group, op.name, "--help")
        assert result.exit_code != 0, (op.operation_id, result.output)
        assert "No such command" in result.output, result.output


async def test_tenant_pinned_token_sees_only_its_tenant(smdev, make_actor):
    a = await make_actor()
    b = await make_actor()
    await smdev.add_env()
    assert (await smdev.login(await smdev.token_for(a))).exit_code == 0
    smdev.transport.requests.clear()
    result = await smdev.run("--env", "local", "tenants", "list-members", "-o", "json")
    assert result.exit_code == 0, result.output
    emails = {row["email"] for row in _items(result.output)}
    assert a.email in emails
    assert b.email not in emails

    smdev.transport.requests.clear()
    other = await smdev.run("--env", "local", "--tenant", "b", "tenants", "list-members")
    assert other.exit_code == 1
    assert "login" in other.output.lower()
    assert smdev.transport.requests == []


async def test_edited_env_url_sends_nothing(smdev, make_actor):
    await _ready(smdev, make_actor)
    await smdev.add_env("http://localhost")
    result = await smdev.run("--env", "local", "whoami")
    assert result.exit_code == 1, result.output
    assert "login --token" in result.output
    assert smdev.transport.requests == []


async def test_put_part_takes_a_raw_body_file(smdev, make_actor, tmp_path):
    ops = {op.operation_id: op for op in parse_operations(load_schema(SCHEMA_PATH))}
    assert ops["file_storage_put_part"].body_kind == "raw"
    await _ready(smdev, make_actor)
    part = tmp_path / "part.bin"
    part.write_bytes(b"abc")
    result = await smdev.run(
        "--env", "local", "file-storage", "put-part", "sid", "1", "--body-file", str(part),
        "--dry-run",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "body-file" in result.output and "application/octet-stream" in result.output
