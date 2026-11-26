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


def test_exactly_the_cap_lists_every_field():
    fields, more = body_field_summary({"properties": _props(MAX_HELP_FIELDS)}, {})
    assert len(fields) == MAX_HELP_FIELDS and more == 0


def test_one_over_the_cap_reports_the_rest():
    fields, more = body_field_summary({"properties": _props(MAX_HELP_FIELDS + 1)}, {})
    assert len(fields) == MAX_HELP_FIELDS and more == 1


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
    assert set_addressable("full_name") and set_addressable("full name")
    for name in ("a.b", "a=b", "a\nb", ""):
        assert not set_addressable(name)


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
