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
