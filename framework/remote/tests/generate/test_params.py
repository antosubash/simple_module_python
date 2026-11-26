from pathlib import Path

import click
import pytest
from simple_module_remote.generate.naming import command_name
from simple_module_remote.generate.operations import Operation, Param, parse_operations
from simple_module_remote.generate.params import click_params_for, param_map, returns_list
from simple_module_remote.schema.loader import load_schema

ROOT = load_schema(Path(__file__).parent / "fixtures" / "mini_openapi.json")


@pytest.fixture(scope="module")
def ops() -> dict[str, Operation]:
    return {o.operation_id: o for o in parse_operations(ROOT)}


def by_name(params):
    return {p.name: p for p in params}


def make_op(**kw) -> Operation:
    base = {
        "operation_id": "x", "method": "GET", "path": "/api/x", "group": "g", "name": "n",
        "params": (), "body_kind": "none", "body_schema": None, "summary": "",
        "description": "", "safe": False, "confirm": False, "token_capable": True,
    }  # fmt: skip
    base.update(kw)
    return Operation(**base)


def test_query_options_and_types(ops):
    params = by_name(click_params_for(ops["users_list_users"]))
    assert isinstance(params["q_role"].type, click.Choice)
    assert params["q_tag"].multiple is True
    assert params["q_page"].type is click.INT
    assert params["q_page"].required is True


def test_path_arguments_in_order(ops):
    args = [p for p in click_params_for(ops["users_delete_user"]) if isinstance(p, click.Argument)]
    assert [a.name for a in args] == ["p_user_id"]


def test_path_order_follows_template():
    op = make_op(
        path="/api/{b}/x/{a}",
        params=(Param("a", "path", True, {}, ""), Param("b", "path", True, {}, "")),
    )
    args = [p.name for p in click_params_for(op) if isinstance(p, click.Argument)]
    assert args == ["p_b", "p_a"]


def test_param_name_collision_prefixed():
    op = make_op(
        params=(Param("json", "query", False, {}, ""), Param("all", "query", False, {}, ""))
    )
    opts = {o for p in click_params_for(op, list_returning=True) for o in getattr(p, "opts", [])}
    assert "--param-json" in opts
    assert "--param-all" in opts
    assert {"--all", "--limit"} <= opts
    assert param_map(op)["q_json"].name == "json"


def test_body_options_by_kind(ops):
    def opts(op):
        return {o for p in click_params_for(op) for o in getattr(p, "opts", [])}

    assert {"--json", "--file", "--set", "--set-json"} <= opts(ops["users_create_user"])
    assert {"--upload", "--set"} <= opts(ops["file_storage_upload"])
    assert {"--body-file", "--content-type"} <= opts(ops["file_storage_put_raw"])
    assert "--json" not in opts(ops["users_delete_user"])
    assert {"--dry-run", "--output", "-o", "--columns", "-q", "--out", "--yes"} <= opts(
        ops["users_delete_user"]
    )


def test_unexpressible_operation_still_builds(ops):
    opts = {o for p in click_params_for(ops["users_choose"]) for o in getattr(p, "opts", [])}
    assert "--json" in opts


def test_returns_list():
    root = {
        "paths": {
            "/a": {"get": {"responses": {"200": {"content": {"application/json": {
                "schema": {"type": "array", "items": {}}}}}}}},
            "/b": {"get": {"responses": {"200": {"content": {"application/json": {
                "schema": {"$ref": "#/c/Page"}}}}}}},
            "/c": {"get": {"responses": {"200": {"content": {"application/json": {
                "schema": {"type": "object"}}}}}}},
        },
        "c": {"Page": {"type": "object", "properties": {"items": {"type": "array"}}}},
    }  # fmt: skip
    assert returns_list(make_op(path="/a"), root)
    assert returns_list(make_op(path="/b"), root)
    assert not returns_list(make_op(path="/c"), root)
    assert not returns_list(make_op(path="/a", method="POST"), root)


def test_json_media_with_params_and_suffix():
    def kind(media):
        doc = {
            "paths": {
                "/api/x": {
                    "post": {"requestBody": {"content": {media: {"schema": {"type": "object"}}}}}
                }
            }
        }
        return parse_operations(doc)[0].body_kind

    assert kind("application/json; charset=utf-8") == "json"
    assert kind("application/vnd.api+json") == "json"
    assert kind("application/octet-stream") == "raw"


@pytest.mark.parametrize("op_id", ["", "___", "!!"])
def test_command_name_never_empty(op_id):
    assert command_name(op_id, None, None, method="get", path="/api/x") == "get-api-x"
    assert command_name(op_id, None, None) == "operation"


def test_help_is_a_reserved_option_name():
    op = make_op(params=(Param("help", "query", False, {"type": "string"}, ""),))
    flags = [o for p in click_params_for(op) for o in p.opts]
    assert "--param-help" in flags
    assert "--help" not in flags


def _list_root(media: str) -> dict:
    return {
        "paths": {
            "/api/x": {
                "get": {
                    "responses": {
                        "200": {"content": {media: {"schema": {"type": "array", "items": {}}}}}
                    }
                }
            }
        }
    }


@pytest.mark.parametrize(
    "media", ["application/json", "application/json; charset=utf-8", "application/problem+json"]
)
def test_returns_list_json_media_variants(media):
    assert returns_list(make_op(), _list_root(media)) is True


def test_returns_list_ignores_non_json_media():
    assert returns_list(make_op(), _list_root("text/csv")) is False
