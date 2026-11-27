"""The body-field summary behind --help (#1241)."""

import io

from simple_module_remote.generate.body_help import (
    MAX_HELP_FIELDS,
    BodyField,
    body_field_summary,
    set_addressable,
)


def _props(count: int, **extra) -> dict:
    return {f"f{n:02d}": {"type": "string"} for n in range(count)} | extra


def test_the_documented_cap_is_forty():
    assert MAX_HELP_FIELDS == 40


def test_exactly_the_cap_lists_every_field():
    fields, more = body_field_summary({"properties": _props(40)}, {})
    assert len(fields) == 40 and more == 0


def test_one_over_the_cap_reports_the_rest():
    fields, more = body_field_summary({"properties": _props(41)}, {})
    assert len(fields) == 40 and more == 1


def test_read_only_fields_do_not_use_up_the_cap():
    read_only = {f"r{n:02d}": {"type": "string", "readOnly": True} for n in range(MAX_HELP_FIELDS)}
    fields, more = body_field_summary({"properties": read_only | {"name": {"type": "string"}}}, {})
    assert fields == [BodyField("name", "string", False)] and more == 0


def test_recursive_array_has_a_bounded_label():
    root = {"components": {"schemas": {"Tree": {"type": "array",
            "items": {"$ref": "#/components/schemas/Tree"}}}}}  # fmt: skip
    body = {"properties": {"tree": {"$ref": "#/components/schemas/Tree"}}}
    (field,), _ = body_field_summary(body, root)
    assert field.kind == "list of list of list of list of list"  # MAX_LABEL_DEPTH = 4


def test_nullable_type_array_shows_its_type():
    body = {"properties": {"n": {"type": ["integer", "null"]}}}
    assert body_field_summary(body, {})[0] == [BodyField("n", "integer", False)]


def test_all_of_and_nullable_wrappers_are_read():
    root = {"components": {"schemas": {
        "Base": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
    }}}  # fmt: skip
    body = {"anyOf": [{"type": "null"}, {"allOf": [
        {"$ref": "#/components/schemas/Base"},
        {"properties": {"tags": {"type": "array", "items": {"type": "string"}}}},
    ]}]}  # fmt: skip
    fields, _ = body_field_summary(body, root)
    assert fields == [BodyField("id", "string", True), BodyField("tags", "list of string", False)]


def test_keys_set_cannot_address():
    for name in ("full_name", "full name", "tab\there"):
        assert set_addressable(name)
    for name in ("a.b", "a=b", ""):
        assert not set_addressable(name)


def test_properties_beside_a_nullable_wrapper_are_kept():
    from simple_module_remote.generate.body import build_json_body, missing_required

    body = {"properties": {"n": {"type": "integer"}}, "required": ["n"],
            "anyOf": [{"type": "null"}, {"properties": {"m": {"type": "integer"}}}]}  # fmt: skip
    fields, _ = body_field_summary(body, {})
    assert [f.name for f in fields] == ["n", "m"]
    sent = build_json_body(
        json_arg=None,
        file_arg=None,
        sets=("n=1", "m=2"),
        set_jsons=(),
        body_schema=body,
        root={},
        stdin=io.StringIO(""),
    )
    assert sent == {"n": 1, "m": 2}
    assert missing_required({"m": 2}, body, {}) == ["n"]


def test_required_fields_from_all_of_are_enforced():
    from simple_module_remote.generate.body import missing_required

    body = {"allOf": [{"required": ["b", "a"], "properties": {"a": {}, "b": {}}}]}
    assert missing_required({}, body, {}) == ["b", "a"]  # schema order


def test_set_coerces_fields_help_finds_through_all_of_and_nullable():
    """What --help lists is what --set coerces: a composed integer is sent as one."""
    from simple_module_remote.generate.body import build_json_body

    body = {"anyOf": [{"type": "null"}, {"allOf": [
        {"properties": {"n": {"type": "integer"}}},
        {"properties": {"tags": {"type": "array", "items": {"type": "string"}}}},
    ]}]}  # fmt: skip
    sent = build_json_body(
        json_arg=None,
        file_arg=None,
        sets=("n=5", "tags=a", "full name=x"),
        set_jsons=(),
        body_schema=body,
        root={},
        stdin=io.StringIO(""),
    )
    assert sent == {"n": 5, "tags": ["a"], "full name": "x"}
