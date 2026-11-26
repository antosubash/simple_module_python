"""Click parameters for an :class:`Operation`."""

from __future__ import annotations

import re

import click
from click.core import ParameterSource

from simple_module_remote.generate.naming import kebab_name, snake_name
from simple_module_remote.generate.operations import Operation, Param, is_json_media
from simple_module_remote.output.render import OUTPUT_FORMATS
from simple_module_remote.output.sanitize import sanitize
from simple_module_remote.schema.loader import resolve_ref

__all__ = [
    "PATH_VAR",
    "RESERVED_OPTIONS",
    "click_params_for",
    "json_response_schema",
    "param_map",
    "returns_list",
    "success_is_json",
]

RESERVED_OPTIONS: frozenset[str] = frozenset(
    {
        "output", "columns", "q", "out", "yes", "dry-run", "all", "limit", "json",
        "file", "set", "set-json", "upload", "body-file", "content-type", "help",
    }
)  # fmt: skip

PATH_VAR = re.compile(r"\{([^}]+)\}")  # one ``{param}`` placeholder (name captured)
_SCALARS: dict[str, click.ParamType] = {
    "integer": click.INT,
    "number": click.FLOAT,
    "boolean": click.BOOL,
}


def _flag_only(ctx: click.Context, param: click.Parameter, value: bool) -> bool:
    """``--yes`` counts only when typed on the command line, never from the environment."""
    source = ctx.get_parameter_source(param.name or "")
    return bool(value) and source == ParameterSource.COMMANDLINE


def _slug(param: Param) -> str:
    return snake_name(param.name) or "param"


def _dest(param: Param) -> str:
    prefix = "p" if param.location == "path" else "q"
    return f"{prefix}_{_slug(param)}"


def _ordered(op: Operation) -> list[Param]:
    order = {name: i for i, name in enumerate(PATH_VAR.findall(op.path))}
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
    choices = [str(e) for e in enum] if isinstance(enum, list) else []
    # Choices are printed in help and errors: only single-line printable text is offered.
    if choices and all(c.isprintable() and sanitize(c) == c for c in choices):
        return click.Choice(choices)
    kind = schema.get("type")
    return _SCALARS.get(kind, click.STRING) if isinstance(kind, str) else click.STRING


def _param_option(dest: str, param: Param) -> click.Parameter:
    kebab = kebab_name(param.name) or "param"
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
            click.Option(
                ["--upload", "uploads"],
                multiple=True,
                help="Upload a file: field=path (or field=@path).",
            ),
            click.Option(["--set", "sets"], multiple=True, help="Form field: key=value."),
        ]
    if op.body_kind == "raw":
        return [
            click.Option(["--body-file", "body_file"], help="File to send as the body."),
            click.Option(["--content-type", "content_type"], help="Content-Type of the body."),
        ]
    return []


def _success_response(op: Operation, root: dict) -> dict:
    """The resolved success response object (200, else first 2xx); ``{}`` when absent."""
    node = ((root.get("paths") or {}).get(op.path) or {}).get(op.method.lower()) or {}
    responses = node.get("responses") or {}
    code = "200" if "200" in responses else next((c for c in responses if str(c)[:1] == "2"), None)
    return resolve_ref(root, responses.get(code) or {}) if code else {}


def json_response_schema(op: Operation, root: dict) -> dict | None:
    """The resolved JSON schema of the operation's success response."""
    content = _success_response(op, root).get("content") or {}
    media = next((v for k, v in content.items() if is_json_media(str(k))), None)
    if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
        return None
    return resolve_ref(root, media["schema"])


def success_is_json(op: Operation, root: dict) -> bool:
    """False when the success response declares content but none of it is JSON."""
    content = _success_response(op, root).get("content")
    if not isinstance(content, dict) or not content:
        return True
    return any(is_json_media(str(k)) for k in content)


def returns_list(op: Operation, root: dict) -> bool:
    """True for a GET whose 200 response is an array or an object with an ``items`` array."""
    if op.method != "GET":
        return False
    schema = json_response_schema(op, root) or {}
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
            kebab = _slug(param).upper()
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
            click.Option(
                ["-o", "--output", "output"],
                type=click.Choice(OUTPUT_FORMATS),
                help="Output format.",
            ),
            click.Option(["--columns", "columns"], help="Comma-separated columns to show."),
            click.Option(["-q", "quiet"], is_flag=True, help="Print only identifiers."),
            click.Option(["--out", "out"], help="Write the response body to a file."),
            click.Option(
                ["--yes", "yes"],
                is_flag=True,
                allow_from_autoenv=False,
                callback=_flag_only,
                help="Skip the confirmation prompt.",
            ),
        ]
    )
    if list_returning:
        params.extend(
            [
                click.Option(["--all", "all_pages"], is_flag=True, help="Fetch every page."),
                click.Option(
                    ["--limit", "limit"],
                    type=click.IntRange(min=1),
                    help="Maximum rows (implies --all).",
                ),
            ]
        )
    return params
