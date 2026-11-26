import pytest
from simple_module_remote.generate.naming import RESERVED, command_name, group_name


@pytest.mark.parametrize(
    ("op_id", "tag", "override", "expected"),
    [
        ("tenants_change_role", "Tenants", None, "change-role"),
        ("users_list_users", "Users", None, "list-users"),
        ("feature_flags_flip", "FeatureFlags", None, "flip"),
        ("api_tokens_create", "ApiTokens", None, "create"),
        ("users_list_users", "Users", "ls", "ls"),
        ("ping", None, None, "ping"),
        ("other_thing", "Users", None, "other-thing"),
        ("users_same_get_api_x", "Users", None, "same-get-api-x"),
    ],
)
def test_command_name(op_id, tag, override, expected):
    assert command_name(op_id, tag, override) == expected


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("FeatureFlags", "feature-flags"), ("Users", "users"), ("Meta", "meta"), (None, "host")],
)
def test_group_name(tag, expected):
    assert group_name(tag) == expected


def test_reserved_names():
    assert {"env", "login", "logout", "whoami", "doctor", "schema", "api", "raw"} == RESERVED


@pytest.mark.parametrize("override", ["\x1b[31mevil", "Upper", "-lead", "a b", "x" * 64, ""])
def test_invalid_override_falls_back_to_the_derived_name(override):
    assert command_name("users_list_users", "Users", override) == "list-users"


def test_valid_override_wins():
    assert command_name("users_list_users", "Users", "ls") == "ls"
