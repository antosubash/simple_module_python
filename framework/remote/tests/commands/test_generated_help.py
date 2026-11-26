"""A generated command's --help lists its JSON body fields (#1241)."""

from click.testing import CliRunner


def _help(make_cli, *command: str) -> str:
    result = CliRunner().invoke(make_cli(), [*command, "--help"])
    assert result.exit_code == 0, result.output
    return " ".join(result.output.split())


def test_help_lists_body_fields_and_marks_required(make_cli):
    text = _help(make_cli, "users", "create-user")
    assert "Body fields for --set (* required):" in text
    assert "email* (string)" in text and "address (object)" in text and "meta (object)" in text
    assert "cannot be set with --set" not in text and "more (see the schema)" not in text


def test_help_without_a_json_body_lists_no_fields(make_cli):
    assert "Body fields" not in _help(make_cli, "file-storage", "upload")


def test_help_names_fields_set_cannot_address(make_cli, clean_schema, tmp_path):
    import json

    doc = json.loads(clean_schema.read_text())
    doc["components"]["schemas"]["UserIn"]["properties"]["a.b"] = {"type": "string"}
    doc["components"]["schemas"]["UserIn"]["properties"]["c\rd"] = {"type": "string"}
    path = tmp_path / "odd.json"
    path.write_text(json.dumps(doc))
    result = CliRunner().invoke(make_cli(schema=path), ["users", "create-user", "--help"])
    text = " ".join(result.output.split())
    assert "Empty names and names with . or = cannot be set with --set" in text
    assert "'c\\rd' (string)" in text  # a control character is shown escaped
