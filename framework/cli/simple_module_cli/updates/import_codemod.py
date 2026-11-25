"""Rewrite imports of deprecated framework paths to their area paths (``smpy fix-imports``).

The rename table ships as ``import_renames.json`` beside this file, generated from
the framework's registered layout shims by ``scripts/gen_import_renames.py``, so
the CLI keeps its zero dependency on ``simple_module_core``. Rewrites are
byte-span edits on the original source located through :mod:`ast`; formatting
and comments outside an edited span are preserved. A statement the codemod
cannot rewrite safely is reported as ``manual`` and left untouched.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from importlib.resources import files

_DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+")


def load_renames() -> dict[str, str]:
    """Old dotted module path -> new dotted module path."""
    raw = files(__package__).joinpath("import_renames.json").read_text(encoding="utf-8")
    return {old: entry["new"] for old, entry in json.loads(raw)["renames"].items()}


@dataclass
class Rewrite:
    """The outcome for one source file."""

    source: str
    changes: list[str] = field(default_factory=list)
    manual: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def resolve(name: str, renames: dict[str, str]) -> str | None:
    """New path for ``name``, matching it exactly or by a renamed package prefix."""
    if name in renames:
        return renames[name]
    head = name
    while "." in head:
        head = head.rsplit(".", 1)[0]
        if head in renames:
            return renames[head] + name[len(head) :]
    return None


class _Edits:
    def __init__(self, source: str) -> None:
        self.data = source.encode("utf-8")
        self.lines: list[int] = [0]
        for i, byte in enumerate(self.data):
            if byte == 0x0A:
                self.lines.append(i + 1)
        self.edits: list[tuple[int, int, bytes]] = []

    def offset(self, lineno: int, col: int) -> int:
        return self.lines[lineno - 1] + col

    def span(self, node: ast.AST) -> tuple[int, int]:
        start = self.offset(node.lineno, node.col_offset)
        end = self.offset(node.end_lineno, node.end_col_offset)
        return start, end

    def text(self, start: int, end: int) -> str:
        return self.data[start:end].decode("utf-8")

    def add(self, start: int, end: int, replacement: str) -> None:
        self.edits.append((start, end, replacement.encode("utf-8")))

    def apply(self) -> str:
        out = self.data
        last = len(out) + 1
        for start, end, new in sorted(self.edits, reverse=True):
            if end > last:  # overlapping edit: keep the later-starting one only
                continue
            out = out[:start] + new + out[end:]
            last = start
        return out.decode("utf-8")


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _alias_text(alias: ast.alias) -> str:
    return f"{alias.name} as {alias.asname}" if alias.asname else alias.name


def _stands_alone(edits: _Edits, start: int, end: int) -> bool:
    """True when the statement owns its lines (no ``;`` neighbours)."""
    line_start = edits.data.rfind(b"\n", 0, start) + 1
    line_end = edits.data.find(b"\n", end)
    tail = edits.data[end : len(edits.data) if line_end < 0 else line_end].strip()
    return not edits.data[line_start:start].strip() and (not tail or tail.startswith(b"#"))


def _rewrite_import(node: ast.Import, edits: _Edits, renames, result, bare: dict) -> None:
    for alias in node.names:
        new = resolve(alias.name, renames)
        if new is None:
            continue
        start, _ = edits.span(alias)
        if edits.text(start, start + len(alias.name)) != alias.name:
            result.manual.append(f"line {node.lineno}: import {alias.name}")
            continue
        edits.add(start, start + len(alias.name), new)
        result.changes.append(f"line {node.lineno}: {alias.name} -> {new}")
        if alias.asname is None:
            bare[alias.name] = new


def _rewrite_from(node: ast.ImportFrom, edits: _Edits, renames, result) -> None:
    if node.level or node.module is None:
        return
    start, end = edits.span(node)
    new_module = resolve(node.module, renames)
    if new_module is not None:
        match = re.match(rf"from\s+({re.escape(node.module)})\b", edits.text(start, end))
        if match is None:
            result.manual.append(f"line {node.lineno}: from {node.module} import ...")
            return
        mod_start = start + len(edits.text(start, end)[: match.start(1)].encode("utf-8"))
        edits.add(mod_start, mod_start + len(node.module.encode("utf-8")), new_module)
        result.changes.append(f"line {node.lineno}: {node.module} -> {new_module}")
        return
    moved = [(a, resolve(f"{node.module}.{a.name}", renames)) for a in node.names]
    if not any(new for _, new in moved):
        return
    if not _stands_alone(edits, start, end):
        result.manual.append(f"line {node.lineno}: from {node.module} import ...")
        return
    kept = [_alias_text(a) for a, new in moved if new is None]
    statements = [f"from {node.module} import {', '.join(kept)}"] if kept else []
    for alias, new in moved:
        if new is None:
            continue
        parent, leaf = new.rsplit(".", 1)
        bound = alias.asname or alias.name
        statements.append(
            f"from {parent} import {leaf}" + ("" if bound == leaf else f" as {bound}")
        )
        result.changes.append(f"line {node.lineno}: {node.module}.{alias.name} -> {new}")
    indent = " " * node.col_offset
    edits.add(start, end, f"\n{indent}".join(statements))


def _rewrite_string(node: ast.Constant, edits: _Edits, renames, result) -> None:
    value = node.value
    if not isinstance(value, str) or not _DOTTED.fullmatch(value):
        return
    new = resolve(value, renames)
    if new is None:
        return
    start, end = edits.span(node)
    literal = edits.text(start, end)
    if len(literal) < 2 or literal[0] not in "'\"" or literal[1:-1] != value:
        result.manual.append(f"line {node.lineno}: string {value!r}")
        return
    edits.add(start + 1, end - 1, new)
    result.changes.append(f"line {node.lineno}: '{value}' -> '{new}'")


def rewrite_source(source: str, renames: dict[str, str]) -> Rewrite:
    """Rewrite deprecated imports, bare-import attribute chains and dotted strings."""
    result = Rewrite(source)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        result.manual.append(f"not parsed: {exc.msg} (line {exc.lineno})")
        return result
    edits = _Edits(source)
    bare: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _rewrite_import(node, edits, renames, result, bare)
        elif isinstance(node, ast.ImportFrom):
            _rewrite_from(node, edits, renames, result)
        elif isinstance(node, ast.Constant):
            _rewrite_string(node, edits, renames, result)
    if bare:
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and (old := _dotted(node)) in bare:
                edits.add(*edits.span(node), bare[old])
                result.changes.append(f"line {node.lineno}: {old} -> {bare[old]}")
    if result.changes:
        result.source = edits.apply()
    return result
