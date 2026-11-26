import json

from simple_module_remote.schema.loader import load_schema, resolve_ref

DOC = {
    "components": {
        "schemas": {
            "A": {"$ref": "#/components/schemas/B"},
            "B": {"type": "object"},
            "Loop": {"$ref": "#/components/schemas/Loop2"},
            "Loop2": {"$ref": "#/components/schemas/Loop"},
        }
    }
}


def test_load_schema(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps(DOC))
    assert load_schema(path) == DOC


def test_ref_chain_followed():
    assert resolve_ref(DOC, {"$ref": "#/components/schemas/A"}) == {"type": "object"}


def test_plain_node_unchanged():
    assert resolve_ref(DOC, {"type": "string"}) == {"type": "string"}


def test_cycle_and_dangling_are_safe():
    assert resolve_ref(DOC, {"$ref": "#/components/schemas/Loop"}) == {}
    assert resolve_ref(DOC, {"$ref": "#/nope"}) == {}
    assert resolve_ref(DOC, {"$ref": "http://x/y"}) == {}
