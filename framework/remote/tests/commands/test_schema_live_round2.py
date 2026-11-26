"""Live schema trust, review round 2: route identity, fetch errors, shapes, text, env."""

import json

import httpx
import pytest
from click.testing import CliRunner
from simple_module_remote.commands.api_cmd import _synthetic
from simple_module_remote.config.paths import cache_dir
from simple_module_remote.generate.operations import parse_operations
from simple_module_remote.generate.params import _value_type
from simple_module_remote.generate.prepare import field_list
from simple_module_remote.generate.trust import hint_index, trusted_hints
from simple_module_remote.generate.validate import schema_problems
from simple_module_remote.schema.cache import open_cache, write_to


def _doc(paths: dict) -> dict:
    return {"openapi": "3.1.0", "paths": paths}


def _op(**marks) -> dict:
    return {"operationId": "op", "x-sm-token": True, **marks}


def _only(doc: dict):
    (op,) = parse_operations(doc)
    return op


def test_placeholder_rename_keeps_bundled_hints():
    bundled = _doc({"/api/a/{id}": {"post": _op(**{"x-cli-safe": True})},
                    "/api/b/{id}": {"post": _op(**{"x-cli-confirm": True})}})  # fmt: skip
    index = hint_index(bundled)
    renamed = trusted_hints(_only(_doc({"/api/a/{x}": {"post": _op()}})), index)
    assert renamed.safe
    confirm = trusted_hints(_only(_doc({"/api/b/{other}": {"post": _op()}})), index)
    assert confirm.confirm and not confirm.safe
    reshaped = trusted_hints(_only(_doc({"/api/a/{x}/more": {"post": _op()}})), index)
    assert not reshaped.safe


def test_api_path_matching_two_templates_is_not_waived():
    safe = {"x-cli-safe": True}
    both = _doc({"/api/a/literal": {"post": _op(**safe)}, "/api/a/{id}": {"post": _op(**safe)}})
    assert not _synthetic("POST", "/api/a/literal", [], both, both).safe
    assert _synthetic("POST", "/api/a/other", [], both, both).safe
    renamed = _doc({"/api/a/{x}": {"post": _op()}})
    assert _synthetic("POST", "/api/a/other", [], renamed, both).safe  # same shape, renamed


class _Broken(httpx.SyncByteStream):
    def __iter__(self):
        yield b'{"openapi": "3.1.0", '
        raise httpx.ReadError("connection reset \x1b[2J")


def test_stream_error_while_reading_is_a_network_failure(live, run_live):
    synced, *_ = run_live(live, response=httpx.Response(200, stream=_Broken()))
    assert synced.exit_code == 3, synced.output
    assert "reading the schema failed: ReadError" in synced.output
    assert "\x1b" not in synced.output


BAD_SHAPES = [
    {"type": "object", "properties": []},
    {"type": "object", "required": "email"},
    {"type": "string", "enum": "abc"},
    {"type": "array", "items": "x"},
    {"anyOf": {"type": "string"}},
    {"type": 3},
]


@pytest.mark.parametrize("shape", BAD_SHAPES)
def test_schema_problems_finds_bad_body_shapes(shape):
    body = {"content": {"application/json": {"schema": shape}}}
    assert schema_problems(_doc({"/api/x": {"post": {**_op(), "requestBody": body}}}))


@pytest.mark.parametrize(
    "params",
    [
        "notalist",
        [{"name": "q", "in": "query", "schema": "string"}],
        [{"in": "query"}],
        [{"name": "q", "in": "query", "schema": {"enum": "a"}}],
    ],
)
def test_schema_problems_finds_bad_parameters(params):
    assert schema_problems(_doc({"/api/x": {"get": {**_op(), "parameters": params}}}))


def test_the_test_schema_has_no_problems(live):
    assert schema_problems(live) == []


def test_unusable_shapes_are_refused_at_sync(live, run_live):
    live["components"]["schemas"]["UserIn"]["properties"] = ["email"]
    synced, *_ = run_live(live)
    assert synced.exit_code == 1 and "the schema is unusable" in synced.output
    assert not (cache_dir("smdev") / "dev" / "openapi.json").exists()


def test_unusable_cached_shapes_fall_back_to_bundled(live, run_live):
    _, _, _, runner, cli = run_live(live, sync=False)
    live["components"]["schemas"]["UserIn"]["required"] = "email"
    with open_cache("smdev", "dev", create=True) as store:
        write_to(store, "http://localhost:8000", "http://localhost:8000",
                 json.dumps(live).encode(), None)  # fmt: skip
    result = runner.invoke(cli, ["schema", "status"])
    assert "source:      bundled" in result.output and "malformed" in result.output
    assert "'required' is not a list" in result.stderr


@pytest.mark.parametrize("bad", ["a\nb", "a\tb", "a\x1bb"])
def test_enum_choices_must_be_single_line_printable(bad):
    import click

    assert not isinstance(_value_type({"enum": [bad, "ok"]}), click.Choice)
    assert isinstance(_value_type({"enum": ["ok", "fine"]}), click.Choice)


def test_field_names_are_escaped_in_usage_errors():
    shown = field_list(["email", "evil\n\x1b[2Jname"])
    assert shown.startswith("email, ") and "\n" not in shown and "\x1b" not in shown


def test_conflicting_env_flags_are_refused(live, run_live):
    _, _, _, runner, cli = run_live(live, sync=False)
    clash = runner.invoke(cli, ["--env", "dev", "schema", "sync", "--env", "other"])
    assert clash.exit_code == 1 and "conflicting environments" in clash.output
    same = runner.invoke(cli, ["--env", "dev", "schema", "sync", "--env", "dev"])
    assert same.exit_code == 0, same.output


def test_callable_default_map_env_is_called(live, run_live):
    _, _, seen, runner, cli = run_live(live)
    runner.invoke(cli, ["env", "add", "other", "--url", "http://127.0.0.1:9"])
    runner.invoke(cli, ["env", "use", "other"])
    cli.context_settings["default_map"] = {"env": lambda: "dev"}
    result = CliRunner().invoke(cli, ["host", "ping"])
    assert result.exit_code == 5, result.output
    assert seen[-1].url.host == "localhost"
