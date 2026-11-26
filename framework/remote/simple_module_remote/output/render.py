"""Render API results as a table, JSON, YAML or bare identifiers."""

from __future__ import annotations

import json
from typing import Any, Literal, TextIO

import yaml
from rich.console import Console
from rich.table import Table

__all__ = ["OUTPUT_FORMATS", "render"]

Format = Literal["table", "json", "yaml", "id"]
OUTPUT_FORMATS: tuple[str, ...] = ("table", "json", "yaml", "id")
MAX_AUTO_COLUMNS = 8
ID_KEY = "id"


def _rows(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    return None


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return json.dumps(value, default=str)
    return str(value)


def _auto_columns(rows: list[Any]) -> list[str]:
    first = next((r for r in rows if isinstance(r, dict)), {})
    scalars = [k for k, v in first.items() if not isinstance(v, dict | list)]
    return scalars[:MAX_AUTO_COLUMNS]


def _table(data: Any, columns: list[str] | None, out: TextIO) -> None:
    console = Console(file=out, highlight=False, color_system=None, soft_wrap=False)
    rows = _rows(data)
    table = Table(show_header=True, header_style="bold")
    if rows is None:
        table.add_column("key")
        table.add_column("value")
        pairs = data.items() if isinstance(data, dict) else [("value", data)]
        for key, value in pairs:
            table.add_row(str(key), _cell(value))
    elif rows and all(isinstance(r, dict) for r in rows):
        cols = columns or _auto_columns(rows)
        for col in cols:
            table.add_column(col)
        for row in rows:
            table.add_row(*(_cell(row.get(col)) for col in cols))
    else:
        table.add_column("value")
        for row in rows:
            table.add_row(_cell(row))
    console.print(table)


def _ids(data: Any, out: TextIO) -> None:
    rows = _rows(data)
    for item in rows if rows is not None else [data]:
        value = item.get(ID_KEY) if isinstance(item, dict) else item
        if value is not None:
            out.write(f"{value}\n")


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
        out.write(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    elif chosen == "table":
        _table(data, columns, out)
    else:
        out.write(json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n")
