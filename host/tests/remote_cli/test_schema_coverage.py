"""The bundled schema stays in step with the app and maps to one command per operation."""

from __future__ import annotations

from click.testing import CliRunner
from simple_module_remote.generate.operations import (
    cli_operations,
    find_collisions,
    parse_operations,
)
from simple_module_remote.schema.loader import load_schema
from smdev_cli import SCHEMA_PATH, make_cli

METHODS = ("get", "put", "post", "delete", "patch")


def _operations(schema: dict) -> dict[tuple[str, str], tuple[str, bool]]:
    return {
        (method, path): (op["operationId"], op.get("x-sm-token") is True)
        for path, item in schema["paths"].items()
        for method, op in item.items()
        if method in METHODS
    }


def test_every_token_operation_has_one_command():
    ops = cli_operations(parse_operations(load_schema(SCHEMA_PATH)))
    assert ops
    assert find_collisions(ops) == []
    runner = CliRunner()
    cli = make_cli()
    for op in ops:
        result = runner.invoke(cli, ["raw", op.group, op.name, "--help"])
        assert result.exit_code == 0, (op.operation_id, result.output)
        assert op.path in result.output


def test_bundled_schema_matches_app(app):
    bundled = load_schema(SCHEMA_PATH)
    assert _operations(app.openapi()) == _operations(bundled)
