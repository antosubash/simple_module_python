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
    assert "Quoted names" not in text and "more (see the schema)" not in text


def test_help_without_a_json_body_lists_no_fields(make_cli):
    assert "Body fields" not in _help(make_cli, "file-storage", "upload")
