import io
from pathlib import Path

import pytest
from simple_module_remote.generate.body import BodyError, build_json_body, missing_required
from simple_module_remote.schema.loader import load_schema

ROOT = load_schema(Path(__file__).parent / "fixtures" / "mini_openapi.json")
USER_IN = ROOT["components"]["schemas"]["UserIn"]
SCHEMA = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "is_active": {"type": "boolean"},
        "max": {"type": "integer"},
        "ratio": {"type": "number"},
        "name": {"type": "string"},
        "address": {"$ref": "#/components/schemas/Address"},
    },
}


def build(**kw):
    args = {
        "json_arg": None,
        "file_arg": None,
        "sets": (),
        "set_jsons": (),
        "body_schema": SCHEMA,
        "root": ROOT,
        "stdin": io.StringIO(""),
    }
    args.update(kw)
    return build_json_body(**args)


def test_no_input_is_none():
    assert build() is None


def test_set_dotted_creates_nested():
    assert build(sets=["a.b.c=x"]) == {"a": {"b": {"c": "x"}}}


def test_set_coerces_by_schema():
    body = build(sets=["is_active=false", "max=3", "ratio=1.5", "address.city=Rome"])
    assert body == {"is_active": False, "max": 3, "ratio": 1.5, "address": {"city": "Rome"}}


@pytest.mark.parametrize(("raw", "expected"), [("YES", True), ("0", False), ("No", False)])
def test_boolean_forms(raw, expected):
    assert build(sets=[f"is_active={raw}"]) == {"is_active": expected}


def test_bad_coercion_names_key():
    with pytest.raises(BodyError, match=r"max.*integer"):
        build(sets=["max=abc"])
    with pytest.raises(BodyError, match=r"is_active.*boolean"):
        build(sets=["is_active=maybe"])


def test_set_null():
    assert build(sets=["max=null"]) == {"max": None}


def test_set_missing_equals_names_flag():
    with pytest.raises(BodyError, match="--set"):
        build(sets=["oops"])


def test_set_at_file(tmp_path):
    f = tmp_path / "v.txt"
    f.write_text("hello\n")
    assert build(sets=[f"name=@{f}"]) == {"name": "hello"}


def test_set_at_stdin():
    assert build(sets=["name=@-"], stdin=io.StringIO("piped\n")) == {"name": "piped"}


def test_traverse_non_dict_raises():
    with pytest.raises(BodyError, match="not an object"):
        build(sets=["name=x", "name.sub=y"])


def test_merge_order(tmp_path):
    f = tmp_path / "b.json"
    f.write_text('{"a": 2, "b": 2, "c": 2}')
    body = build(
        json_arg='{"a": 1, "z": 1}',
        file_arg=str(f),
        set_jsons=['b={"x": 1}'],
        sets=["c=set"],
    )
    assert body == {"a": 2, "z": 1, "b": {"x": 1}, "c": "set"}


def test_file_dash_reads_stdin():
    assert build(file_arg="-", stdin=io.StringIO('{"name": "n"}')) == {"name": "n"}


def test_file_and_set_stdin_conflict():
    with pytest.raises(BodyError, match="stdin"):
        build(file_arg="-", sets=["name=@-"])


def test_missing_required_reported():
    assert missing_required({}, USER_IN, ROOT) == ["email"]
    assert missing_required({"email": "a"}, USER_IN, ROOT) == []
    assert missing_required({}, None, ROOT) == []


def test_invalid_json_message():
    with pytest.raises(BodyError, match="--json"):
        build(json_arg="{nope")
    with pytest.raises(BodyError, match="--set-json a"):
        build(set_jsons=["a={nope"])


def test_unknown_schema_leaves_strings():
    one_of = {"oneOf": [{"type": "object"}]}
    assert build(sets=["max=3"], body_schema=one_of) == {"max": "3"}


def test_set_unwraps_optional_anyof():
    schema = {
        "type": "object",
        "properties": {"n": {"anyOf": [{"type": "integer"}, {"type": "null"}]}},
    }
    assert build(sets=["n=3"], body_schema=schema) == {"n": 3}
    with pytest.raises(BodyError):
        build(sets=["n=x"], body_schema=schema)


def test_set_unwraps_oneof_ref_branch():
    schema = {
        "type": "object",
        "properties": {
            "n": {"oneOf": [{"$ref": "#/components/schemas/Address"}, {"type": "null"}]}
        },
    }
    assert build(sets=["n.city=Rome"], body_schema=schema) == {"n": {"city": "Rome"}}


def test_set_multiple_branches_stays_string():
    schema = {
        "type": "object",
        "properties": {"n": {"anyOf": [{"type": "integer"}, {"type": "string"}]}},
    }
    assert build(sets=["n=3"], body_schema=schema) == {"n": "3"}


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "Infinity"])
def test_set_rejects_non_finite_number(raw):
    with pytest.raises(BodyError, match="expected number"):
        build(sets=[f"ratio={raw}"])
