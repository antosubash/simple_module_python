"""Render API results as a table, JSON, YAML or bare identifiers."""

from __future__ import annotations

import json
from typing import Any, Literal, TextIO

import yaml
from rich.console import Console
from rich.table import Table
from rich.text import Text

from simple_module_remote.output.sanitize import sanitize, sanitize_for

__all__ = ["OUTPUT_FORMATS", "NoIdentifierError", "UnknownColumnError", "render"]

Format = Literal["table", "json", "yaml", "id"]
OUTPUT_FORMATS: tuple[str, ...] = ("table", "json", "yaml", "id")
MAX_AUTO_COLUMNS = 8
MAX_CELL_CHARS = 200
ID_KEYS = ("id", "name", "key", "slug", "email")
NO_IDENTIFIER = "no identifier field in the response; use -o json"
UNSAFE_IDENTIFIER = (
    "identifier contains control characters or is not a string or number; use -o json"
)


class UnknownColumnError(ValueError):
    """``--columns`` named a field the rows do not have."""


class NoIdentifierError(ValueError):
    """``-o id`` was asked for data that has none of the :data:`ID_KEYS`."""


def _rows(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return None


def _text(value: Any) -> Text:
    return Text(sanitize(_cell(value)))


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = json.dumps(value, default=str) if isinstance(value, dict | list) else str(value)
    if len(text) > MAX_CELL_CHARS:
        return text[: MAX_CELL_CHARS - 1] + "…"
    return text


def _auto_columns(rows: list[Any]) -> list[str]:
    first = next((r for r in rows if isinstance(r, dict)), {})
    scalars = [k for k, v in first.items() if not isinstance(v, dict | list)]
    return scalars[:MAX_AUTO_COLUMNS]


def _check_columns(columns: list[str], rows: list[Any]) -> None:
    known = {key for row in rows if isinstance(row, dict) for key in row}
    unknown = [c for c in columns if c not in known]
    if unknown:
        raise UnknownColumnError(
            f"unknown column {', '.join(unknown)}; available: {', '.join(sorted(known))}"
        )


def _table(data: Any, columns: list[str] | None, out: TextIO) -> None:
    console = Console(file=out, highlight=False, color_system=None, soft_wrap=False)
    rows = _rows(data)
    table = Table(show_header=True, header_style="bold")
    if rows is not None and not rows:
        out.write("no results\n")
        return
    if rows is None:
        table.add_column(Text("key"))
        table.add_column(Text("value"))
        pairs = data.items() if isinstance(data, dict) else [("value", data)]
        if columns and isinstance(data, dict):
            _check_columns(columns, [data])
            pairs = [(k, v) for k, v in pairs if k in columns]
        for key, value in pairs:
            table.add_row(_text(key), _text(value))
    elif rows and all(isinstance(r, dict) for r in rows):
        cols = columns or _auto_columns(rows)
        if columns:
            _check_columns(columns, rows)
        for col in cols:
            table.add_column(Text(sanitize(col)))
        for row in rows:
            table.add_row(*(_text(row.get(col)) for col in cols))
    else:
        table.add_column(Text("value"))
        for row in rows:
            table.add_row(_text(row))
    console.print(table)


def _identifier(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    return next((item[k] for k in ID_KEYS if item.get(k) is not None), None)


def _plain_identifier(value: Any) -> bool:
    """A string or integer with no control characters (a newline would forge a second id)."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        return False
    return not any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in str(value))


def _ids(data: Any, out: TextIO) -> None:
    rows = _rows(data)
    values = [_identifier(item) for item in (rows if rows is not None else [data])]
    if any(value is None for value in values):
        raise NoIdentifierError(NO_IDENTIFIER)
    if not all(_plain_identifier(value) for value in values):
        raise NoIdentifierError(UNSAFE_IDENTIFIER)
    for value in values:
        out.write(sanitize_for(out, f"{value}") + "\n")


def render(
    data: Any,
    *,
    fmt: Format | None,
    columns: list[str] | None,
    quiet: bool,
    is_tty: bool,
    out: TextIO,
) -> None:
    """Write ``data`` to ``out``; a table by default for lists on a terminal, else JSON."""
    chosen: str | None = "id" if quiet else fmt
    if chosen is None:
        chosen = "table" if is_tty and _rows(data) is not None else "json"
    if chosen == "id":
        _ids(data, out)
    elif chosen == "yaml":
        out.write(sanitize_for(out, yaml.safe_dump(data, sort_keys=False, allow_unicode=True)))
    elif chosen == "table":
        _table(data, columns, out)
    else:
        out.write(
            sanitize_for(out, json.dumps(data, indent=2, default=str, ensure_ascii=False)) + "\n"
        )
