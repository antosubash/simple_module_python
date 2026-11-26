"""Click parameters for an :class:`Operation`."""

from __future__ import annotations

import re

import click

from simple_module_remote.generate.naming import snake_name
from simple_module_remote.generate.operations import Operation, Param
from simple_module_remote.schema.loader import resolve_ref

__all__ = ["RESERVED_OPTIONS", "click_params_for", "param_map", "returns_list"]

RESERVED_OPTIONS: frozenset[str] = frozenset(
    {
        "output", "columns", "q", "out", "yes", "dry-run", "all", "limit", "json",
        "file", "set", "set-json", "upload", "body-file", "content-type",
    }
)  # fmt: skip

_PATH_VAR = re.compile(r"\{([^}]+)\}")
_SCALARS: dict[str, click.ParamType] = {
    "integer": click.INT,
    "number": click.FLOAT,
    "boolean": click.BOOL,
}


def _dest(param: Param) -> str:
    prefix = "p" if param.location == "path" else "q"
    return f"{prefix}_{snake_name(param.name) or 'param'}"


def _ordered(op: Operation) -> list[Param]:
    order = {name: i for i, name in enumerate(_PATH_VAR.findall(op.path))}
    paths = sorted(
        (p for p in op.params if p.location == "path"), key=lambda p: order.get(p.name, 99)
    )
    return [*paths, *(p for p in op.params if p.location == "query")]


def param_map(op: Operation) -> dict[str, Param]:
    """Click dest name -> original OpenAPI parameter, for mapping values back."""
    mapping: dict[str, Param] = {}
    for param in _ordered(op):
        dest = _dest(param)
        while dest in mapping:
            dest += "_2"
        mapping[dest] = param
    return mapping


def _value_type(schema: dict) -> click.ParamType:
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return click.Choice([str(e) for e in enum])
    kind = schema.get("type")
    return _SCALARS.get(kind, click.STRING) if isinstance(kind, str) else click.STRING


def _param_option(dest: str, param: Param) -> click.Parameter:
    kebab = snake_name(param.name).replace("_", "-") or "param"
    flag = f"--param-{kebab}" if kebab in RESERVED_OPTIONS else f"--{kebab}"
    schema = param.schema
    multiple = schema.get("type") == "array"
    item = schema.get("items") if multiple else schema
    return click.Option(
        [flag, dest],
        type=_value_type(item if isinstance(item, dict) else {}),
        multiple=multiple,
        required=param.required,
        help=param.description or None,
    )


def _body_options(op: Operation) -> list[click.Parameter]:
    if op.body_kind == "json":
        return [
            click.Option(["--json", "json_arg"], help="Request body as a JSON string."),
            click.Option(
                ["--file", "file_arg"], help="Read the JSON body from a file ('-' = stdin)."
            ),
            click.Option(["--set", "sets"], multiple=True, help="Set a field: key=value (dotted)."),
            click.Option(
                ["--set-json", "set_jsons"], multiple=True, help="Set a field: key=<json>."
            ),
        ]
    if op.body_kind == "multipart":
        return [
            click.Option(["--upload", "uploads"], multiple=True, help="Upload: field=@path."),
            click.Option(["--set", "sets"], multiple=True, help="Form field: key=value."),
        ]
    if op.body_kind == "raw":
        return [
            click.Option(["--body-file", "body_file"], help="File to send as the body."),
            click.Option(["--content-type", "content_type"], help="Content-Type of the body."),
        ]
    return []


def returns_list(op: Operation, root: dict) -> bool:
    """True for a GET whose 200 response is an array or an object with an ``items`` array."""
    if op.method != "GET":
        return False
    node = ((root.get("paths") or {}).get(op.path) or {}).get("get") or {}
    response = resolve_ref(root, ((node.get("responses") or {}).get("200")) or {})
    media = (response.get("content") or {}).get("application/json") or {}
    schema = resolve_ref(root, media.get("schema") or {})
    if schema.get("type") == "array":
        return True
    items = resolve_ref(root, (schema.get("properties") or {}).get("items") or {})
    return items.get("type") == "array"


def click_params_for(op: Operation, *, list_returning: bool = False) -> list[click.Parameter]:
    """Arguments and options for ``op``; pass ``list_returning=returns_list(op, root)``."""
    params: list[click.Parameter] = []
    mapping = param_map(op)
    for dest, param in mapping.items():
        if param.location == "path":
            kebab = (snake_name(param.name) or "param").upper()
            params.append(
                click.Argument([dest], type=_value_type(param.schema), metavar=kebab, required=True)
            )
    params.extend(_param_option(d, p) for d, p in mapping.items() if p.location == "query")
    params.extend(_body_options(op))
    params.extend(
        [
            click.Option(
                ["--dry-run", "dry_run"], is_flag=True, help="Print the request, send nothing."
            ),
            click.Option(["-o", "--output", "output"], help="Output format."),
            click.Option(["--columns", "columns"], help="Comma-separated columns to show."),
            click.Option(["-q", "quiet"], is_flag=True, help="Print only identifiers."),
            click.Option(["--out", "out"], help="Write the response body to a file."),
            click.Option(["--yes", "yes"], is_flag=True, help="Skip the confirmation prompt."),
        ]
    )
    if list_returning:
        params.extend(
            [
                click.Option(["--all", "all_pages"], is_flag=True, help="Fetch every page."),
                click.Option(["--limit", "limit"], type=click.INT, help="Maximum rows."),
            ]
        )
    return params
