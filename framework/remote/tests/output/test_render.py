import io
import json

from simple_module_remote.output.render import render

ROWS = [{"id": 1, "name": "ada", "meta": {"x": 1}}, {"id": 2, "name": "bob", "meta": {}}]


def run(data, **kw) -> str:
    out = io.StringIO()
    args = {"fmt": None, "columns": None, "quiet": False, "is_tty": False, "out": out}
    args.update(kw)
    render(data, **args)
    return out.getvalue()


def test_table_default_on_tty_for_lists():
    text = run(ROWS, is_tty=True)
    assert "name" in text and "ada" in text
    assert "meta" not in text  # nested values are not auto columns
    assert not text.lstrip().startswith("[")


def test_table_default_for_items_envelope_and_columns():
    text = run({"items": ROWS, "total": 2}, is_tty=True, columns=["name"])
    assert "ada" in text and "id" not in text.split("\n")[1]


def test_json_default_off_tty():
    assert json.loads(run(ROWS)) == ROWS


def test_json_default_for_dict_on_tty():
    assert json.loads(run({"a": 1}, is_tty=True)) == {"a": 1}


def test_id_format():
    assert run(ROWS, fmt="id") == "1\n2\n"
    assert run({"items": ROWS}, quiet=True) == "1\n2\n"
    assert run({"id": "x", "n": 1}, fmt="id") == "x\n"


def test_yaml():
    assert run({"a": [1, 2]}, fmt="yaml") == "a:\n- 1\n- 2\n"


def test_auto_columns_capped_at_eight():
    row = {f"c{i}": i for i in range(12)}
    text = run([row], is_tty=True, fmt="table")
    assert "c7" in text and "c8" not in text


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_markup_in_cells_headers_and_keys_is_literal():
    text = run([{"[red]h[/red]": "[bold]x[/bold]"}], is_tty=True)
    assert "[bold]x[/bold]" in text and "[red]h[/red]" in text
    kv = run({"[link=http://evil]k[/link]": "[blue]v"}, is_tty=True, fmt="table")
    assert "[link=http://evil]k[/link]" in kv and "[blue]v" in kv


def test_tty_output_strips_control_sequences_all_formats():
    data = [{"id": "a\x1b]0;t\x07b", "n": "\x1b[31mred\x9b"}]
    for fmt in ("json", "yaml", "id", "table"):
        out = Tty()
        render(data, fmt=fmt, columns=None, quiet=False, is_tty=True, out=out)
        assert "\x1b" not in out.getvalue() and "\x9b" not in out.getvalue()


def test_non_tty_json_is_byte_exact():
    assert json.loads(run([{"a": "\x9b"}])) == [{"a": "\x9b"}]
