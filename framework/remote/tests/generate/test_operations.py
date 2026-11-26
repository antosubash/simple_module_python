from pathlib import Path

import pytest
from simple_module_remote.generate.operations import (
    Operation,
    cli_operations,
    find_collisions,
    parse_operations,
)
from simple_module_remote.schema.loader import load_schema

FIXTURE = Path(__file__).parent / "fixtures" / "mini_openapi.json"


@pytest.fixture(scope="module")
def ops() -> dict[str, Operation]:
    return {o.operation_id: o for o in parse_operations(load_schema(FIXTURE))}


def test_untagged_goes_to_host(ops):
    assert (ops["ping"].group, ops["ping"].name) == ("host", "ping")


def test_names_and_override(ops):
    assert (ops["users_list_users"].group, ops["users_list_users"].name) == ("users", "list-users")
    flip = ops["feature_flags_flip"]
    assert (flip.group, flip.name) == ("feature-flags", "toggle")


def test_token_false_excluded_from_cli_operations():
    all_ops = parse_operations(load_schema(FIXTURE))
    cli_ids = {o.operation_id for o in cli_operations(all_ops)}
    assert "users_session" in {o.operation_id for o in all_ops}
    assert "users_session" not in cli_ids
    assert "users_list_users" in cli_ids


def test_params_merge_and_header_ignored(ops):
    params = {p.name: p for p in ops["users_list_users"].params}
    assert set(params) == {"page", "role", "tag"}
    assert params["page"].required is True  # operation wins over path-level
    assert params["role"].schema["enum"] == ["admin", "member"]
    assert params["tag"].schema["type"] == "array"
    delete = ops["users_delete_user"]
    assert [(p.name, p.location, p.required) for p in delete.params] == [("user_id", "path", True)]


def test_body_kinds_detected(ops):
    assert ops["users_list_users"].body_kind == "none"
    assert ops["users_list_users"].body_schema is None
    assert ops["users_create_user"].body_kind == "json"
    assert ops["file_storage_upload"].body_kind == "multipart"
    assert ops["file_storage_put_raw"].body_kind == "raw"
    assert ops["users_choose"].body_kind == "json"
    assert "oneOf" in (ops["users_choose"].body_schema or {})


def test_ref_resolved(ops):
    schema = ops["users_create_user"].body_schema
    assert schema is not None
    assert schema["required"] == ["email"]
    assert schema["properties"]["address"] == {"$ref": "#/components/schemas/Address"}


def test_flags(ops):
    assert ops["users_list_users"].safe is True
    assert ops["users_delete_user"].confirm is True
    assert ops["users_delete_user"].safe is False
    assert ops["ping"].confirm is False
    assert ops["users_list_users"].method == "GET"
    assert ops["users_list_users"].summary == "List"


def test_collision_reported():
    found = find_collisions(parse_operations(load_schema(FIXTURE)))
    assert ("dup", "same", ["dup_same", "dup_same_get_api_dup_b"]) in found


def test_reserved_group_reported():
    found = find_collisions(parse_operations(load_schema(FIXTURE)))
    assert ("env", "", ["env_show"]) in found


def test_nullable_enum_query_param_becomes_a_choice():
    from simple_module_remote.generate.params import click_params_for

    schema = {
        "components": {"schemas": {"Status": {"type": "string", "enum": ["ok", "failed"]}}},
        "paths": {
            "/api/x": {
                "get": {
                    "x-sm-token": True,
                    "parameters": [
                        {
                            "name": "status",
                            "in": "query",
                            "schema": {
                                "anyOf": [{"$ref": "#/components/schemas/Status"}, {"type": "null"}]
                            },
                        }
                    ],
                }
            }
        },
    }
    (op,) = parse_operations(schema)
    option = next(p for p in click_params_for(op) if p.name == "q_status")
    assert list(option.type.choices) == ["ok", "failed"]
