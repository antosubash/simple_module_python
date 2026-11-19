"""Enforce that magic strings (permissions, role names, Inertia pages, module
dependencies) are declared as named constants rather than inline literals.

Violation patterns — checked only in non-test, non-constants .py files:

  - RequiresPermission("...")       → use a PERM_* constant
  - registry.map_role("...", ...)   → use a ROLE_NAME constant
  - registry.add_group(..., [...])  → permission items must be constants
  - inertia.render("Module/Page")   → verify module identity + an existing TSX page
  - depends_on=[..., "Module", ...] → use a _MODULE_* constant

Usage:
    uv run python scripts/check_hardcoded_strings.py
    uv run python scripts/check_hardcoded_strings.py --root some/subdir
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

# Files whose path contains any of these substrings are skipped entirely.
_SKIP_PATH_PARTS = ("tests/", "test_", "/constants.py", "scripts/")


def _should_skip(path: Path, root: Path) -> bool:
    rel = path.as_posix()
    return any(part in rel for part in _SKIP_PATH_PARTS)


def _literal(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _page_exists(path: Path, component: str) -> bool:
    """Validate against the owning package, without importing application code."""
    parts = component.split("/")
    if any(p in {"", ".", ".."} for p in parts) or "\\" in component:
        return False
    if component.endswith((".test", ".spec")):
        return False
    for parent in path.resolve().parents:
        if not (parent / "pages").is_dir():
            continue
        module_file = parent / "module.py"
        if not module_file.is_file():
            # Host pages have bare keys, unlike module pages.
            return parent.name == "client_app" and (parent / "pages" / f"{component}.tsx").is_file()
        try:
            module_tree = ast.parse(module_file.read_text())
            constants: dict[str, str] = {}
            for source in (parent / "constants.py", parent / "core" / "constants.py", module_file):
                if not source.is_file():
                    continue
                for node in ast.parse(source.read_text()).body:
                    if isinstance(node, ast.Assign) and len(node.targets) == 1:
                        target, value = node.targets[0], _literal(node.value)
                    elif isinstance(node, ast.AnnAssign):
                        target, value = node.target, _literal(node.value)
                    else:
                        continue
                    if isinstance(target, ast.Name) and value is not None:
                        constants[target.id] = value
            for node in ast.walk(module_tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Name) or node.func.id != "ModuleMeta":
                    continue
                for kw in node.keywords:
                    if kw.arg != "name":
                        continue
                    name = _literal(kw.value)
                    if isinstance(kw.value, ast.Name):
                        name = constants.get(kw.value.id)
                    elif isinstance(kw.value, ast.Attribute):
                        name = constants.get(kw.value.attr)
                    if name == parts[0] and len(parts) > 1:
                        return (parent / "pages" / ("/".join(parts[1:]) + ".tsx")).is_file()
        except (OSError, SyntaxError):
            return False
        return False
    return False


def _check_file(path: Path) -> list[tuple[int, str, str]]:
    """Check actual calls, including multiline and single-quoted arguments."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []
    lines = source.splitlines()
    violations: list[tuple[int, str, str]] = []

    def report(node: ast.AST, message: str) -> None:
        violations.append((node.lineno, lines[node.lineno - 1].rstrip(), message))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else ""
        )
        first = node.args[0] if node.args else None
        if name == "RequiresPermission" and _literal(first) is not None:
            report(
                node,
                "permission literal in RequiresPermission() — use a catalogue or PERM_* constant",
            )
        elif name == "map_role" and _literal(first) is not None:
            report(node, "role name literal in registry.map_role() — use a ROLE_NAME constant")
        elif name == "add_group" and len(node.args) > 1:
            if any(_literal(n) is not None for n in ast.walk(node.args[1])):
                report(
                    node,
                    "permission literal in add_group() — use a catalogue or PERM_* constant",
                )
        elif (
            name == "render"
            and isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "inertia"
        ):
            component = first or next(
                (kw.value for kw in node.keywords if kw.arg == "component"), None
            )
            value = _literal(component)
            if value is not None and "/" in value and not _page_exists(path, value):
                report(
                    node,
                    "unverified Inertia page — use an existing Module/Page or a _PAGE_* constant",
                )
        for kw in node.keywords:
            if (
                kw.arg in {"depends_on", "optional_depends_on"}
                and isinstance(kw.value, (ast.List, ast.Tuple))
                and any(_literal(n) is not None for n in kw.value.elts)
            ):
                report(node, "module name literal in depends_on — use a _MODULE_* constant")
    return sorted(violations)


def _list_git_tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [root / line for line in result.stdout.splitlines() if line.endswith(".py")]


def _walk_filesystem(root: Path) -> list[Path]:
    return list(root.rglob("*.py"))


def _collect_candidates(root: Path, use_git: bool) -> list[Path]:
    return _list_git_tracked_files(root) if use_git else _walk_filesystem(root)


def find_violations(
    paths: Iterable[Path],
    root: Path,
) -> list[tuple[Path, int, str, str]]:
    """Return (path, lineno, line, message) for every violation."""
    results: list[tuple[Path, int, str, str]] = []
    for path in paths:
        if _should_skip(path, root):
            continue
        for lineno, line, message in _check_file(path):
            results.append((path, lineno, line, message))
    return results


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    description = (__doc__ or "").splitlines()[0]
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repo root to scan (default: cwd)",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="walk the filesystem instead of using git ls-files",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    root: Path = args.root
    candidates = _collect_candidates(root, use_git=not args.no_git)
    violations = find_violations(candidates, root)
    if not violations:
        print("OK: no hardcoded magic strings found.")
        return 0

    print(f"FAIL: {len(violations)} hardcoded magic string(s) found:\n")
    for path, lineno, line, message in violations:
        rel = path.relative_to(root) if path.is_absolute() else path
        print(f"  {rel.as_posix()}:{lineno}: {message}")
        print(f"    {line}")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
