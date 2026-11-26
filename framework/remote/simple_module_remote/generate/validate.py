"""Shape checks for the parts of a schema that commands consume when they run.

Building the command tree reads only part of the document; bodies, parameters and
responses are read again at invocation (``body.py``, ``params.py``, ``prepare.py``).
A live schema is server-supplied, so these structures are checked up front: a
document with a non-object ``properties``, a non-list ``required``/``enum``, a
non-object parameter schema and the like is refused rather than crashing later.
"""

from __future__ import annotations

from simple_module_remote.generate.operations import METHODS
from simple_module_remote.schema.loader import resolve_ref

__all__ = ["schema_problems"]

MAX_PROBLEMS = 5
_SCHEMA_LISTS = ("anyOf", "oneOf", "allOf")


def _check_schema_node(node: dict, where: str, problems: list[str], stack: list) -> None:
    props = node.get("properties")
    if props is not None:
        if not isinstance(props, dict) or not all(isinstance(v, dict) for v in props.values()):
            problems.append(f"{where}: 'properties' is not an object of schemas")
        else:
            stack.extend((v, f"{where}.properties") for v in props.values())
    required = node.get("required")
    if required is not None and not (
        isinstance(required, list) and all(isinstance(r, str) for r in required)
    ):
        problems.append(f"{where}: 'required' is not a list of names")
    if "enum" in node and not isinstance(node["enum"], list):
        problems.append(f"{where}: 'enum' is not a list")
    kind = node.get("type")
    if kind is not None and not (
        isinstance(kind, str) or (isinstance(kind, list) and all(isinstance(k, str) for k in kind))
    ):
        problems.append(f"{where}: 'type' is not a name or list of names")
    for key in ("items", "additionalProperties"):
        child = node.get(key)
        if key == "items" and child is not None and not isinstance(child, dict):
            problems.append(f"{where}: 'items' is not a schema")
        elif isinstance(child, dict):
            stack.append((child, f"{where}.{key}"))
    for key in _SCHEMA_LISTS:
        branches = node.get(key)
        if branches is None:
            continue
        if not isinstance(branches, list) or not all(isinstance(b, dict) for b in branches):
            problems.append(f"{where}: '{key}' is not a list of schemas")
        else:
            stack.extend((b, f"{where}.{key}") for b in branches)
    ref = node.get("$ref")
    if ref is not None and not isinstance(ref, str):
        problems.append(f"{where}: '$ref' is not text")


def _walk_schemas(root: dict, start: list[tuple[object, str]], problems: list[str]) -> None:
    stack = list(start)
    seen: set[int] = set()
    while stack and len(problems) < MAX_PROBLEMS:
        node, where = stack.pop()
        if not isinstance(node, dict):
            problems.append(f"{where}: schema is not an object")
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        _check_schema_node(node, where, problems, stack)
        if isinstance(node.get("$ref"), str):
            stack.append((resolve_ref(root, node), where))


def _content_schemas(container: object, where: str, problems: list[str], out: list) -> None:
    if container is None:
        return
    if not isinstance(container, dict):
        problems.append(f"{where}: not an object")
        return
    content = container.get("content")
    if content is None:
        return
    if not isinstance(content, dict):
        problems.append(f"{where}: 'content' is not an object")
        return
    for media in content.values():
        if not isinstance(media, dict):
            problems.append(f"{where}: a media type is not an object")
        elif "schema" in media:
            out.append((media["schema"], f"{where} body"))


def _params(root: dict, raw: object, where: str, problems: list[str], out: list) -> None:
    if raw is None:
        return
    if not isinstance(raw, list):
        problems.append(f"{where}: 'parameters' is not a list")
        return
    for item in raw:
        param = resolve_ref(root, item) if isinstance(item, dict) else None
        if not param or not isinstance(param.get("name"), str):
            problems.append(f"{where}: a parameter is not an object with a name")
        elif "schema" in param:
            out.append((param["schema"], f"{where} parameter"))


def schema_problems(root: dict) -> list[str]:
    """Up to :data:`MAX_PROBLEMS` descriptions of unusable structures (empty when fine)."""
    problems: list[str] = []
    schemas: list[tuple[object, str]] = []
    for path, item in (root.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        _params(root, item.get("parameters"), str(path), problems, schemas)
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            where = f"{method.upper()} {path}"
            _params(root, op.get("parameters"), where, problems, schemas)
            body = op.get("requestBody")
            _content_schemas(
                resolve_ref(root, body) if isinstance(body, dict) else body,
                where,
                problems,
                schemas,
            )
            responses = op.get("responses")
            if responses is not None and not isinstance(responses, dict):
                problems.append(f"{where}: 'responses' is not an object")
            for response in (responses or {}).values() if isinstance(responses, dict) else ():
                resolved = resolve_ref(root, response) if isinstance(response, dict) else response
                _content_schemas(resolved, f"{where} response", problems, schemas)
    _walk_schemas(root, schemas, problems)
    return problems[:MAX_PROBLEMS]
