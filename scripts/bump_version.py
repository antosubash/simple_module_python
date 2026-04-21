"""Bump the version of every simple_module package in lockstep.

Walks every framework/*/pyproject.toml, modules/*/pyproject.toml, and
packages/*/package.json. Rewrites:

  * project.version
  * every simple_module_* entry in project.dependencies → "simple_module_*==<version>"
  * every @simple-module-py/* entry in dependencies / devDependencies /
    peerDependencies → "<version>"

Flags:
  --check     exit non-zero if any file is out of sync with <version>
  --dry-run   print a summary of changes but do not write

Usage:
  python scripts/bump_version.py 0.0.2
  python scripts/bump_version.py 0.0.2 --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import tomlkit

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([-.]?(a|b|rc|alpha|beta)\d*)?$")
PY_PKG_PREFIX = "simple_module_"
NPM_SCOPE_PREFIX = "@simple-module-py/"


def _parse_requirement_name(spec: str) -> str:
    """Return the distribution name from a PEP 508 requirement string."""
    base = spec.split(";", 1)[0].strip()
    base = base.split("[", 1)[0]
    for op in ("===", "==", ">=", "<=", "!=", "~=", ">", "<"):
        if op in base:
            return base.split(op, 1)[0].strip()
    return base.strip()


def bump_python_package(pyproject: Path, new_version: str, *, check: bool = False) -> bool:
    """Return True if the file is (or would be) at new_version. Write unless check=True."""
    doc = tomlkit.parse(pyproject.read_text(encoding="utf-8"))
    project = doc.get("project")
    if project is None:
        return True

    changed = False
    current = str(project.get("version", ""))
    if current != new_version:
        changed = True
        project["version"] = new_version

    deps = project.get("dependencies")
    if deps is not None:
        for i, entry in enumerate(deps):
            spec = str(entry)
            name = _parse_requirement_name(spec)
            if name.startswith(PY_PKG_PREFIX):
                want = f"{name}=={new_version}"
                if spec != want:
                    changed = True
                    deps[i] = want

    if check:
        return not changed
    if changed:
        pyproject.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return True


def bump_npm_package(package_json: Path, new_version: str, *, check: bool = False) -> bool:
    data = json.loads(package_json.read_text(encoding="utf-8"))
    changed = False

    if data.get("version") != new_version:
        changed = True
        data["version"] = new_version

    for bucket in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(bucket)
        if not deps:
            continue
        for name, current in list(deps.items()):
            if name.startswith(NPM_SCOPE_PREFIX) and current != new_version:
                changed = True
                deps[name] = new_version

    if check:
        return not changed
    if changed:
        package_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def discover(root: Path) -> tuple[list[Path], list[Path]]:
    py: list[Path] = []
    for base in ("framework", "modules"):
        base_dir = root / base
        if base_dir.is_dir():
            for child in sorted(base_dir.iterdir()):
                if child.is_dir() and (child / "pyproject.toml").exists():
                    py.append(child / "pyproject.toml")
    npm: list[Path] = []
    packages_dir = root / "packages"
    if packages_dir.is_dir():
        for child in sorted(packages_dir.iterdir()):
            if child.is_dir() and (child / "package.json").exists():
                npm.append(child / "package.json")
    return py, npm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="New version string, e.g. 0.0.2")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    if not VERSION_RE.match(args.version):
        print(f"ERROR: '{args.version}' is not a valid version.", file=sys.stderr)
        raise SystemExit(2)

    py_files, npm_files = discover(args.root)
    all_ok = True

    for p in py_files:
        ok = bump_python_package(p, args.version, check=args.check or args.dry_run)
        if args.check and not ok:
            print(f"OUT-OF-SYNC: {p}", file=sys.stderr)
            all_ok = False

    for p in npm_files:
        ok = bump_npm_package(p, args.version, check=args.check or args.dry_run)
        if args.check and not ok:
            print(f"OUT-OF-SYNC: {p}", file=sys.stderr)
            all_ok = False

    if args.check:
        if all_ok:
            print(f"All {len(py_files) + len(npm_files)} packages at {args.version}.")
            return 0
        print("FAIL: one or more packages out of sync.", file=sys.stderr)
        return 1

    total = len(py_files) + len(npm_files)
    if args.dry_run:
        print(
            f"(dry-run) Would bump {len(py_files)} python + "
            f"{len(npm_files)} npm packages to {args.version}."
        )
        return 0

    print(
        f"Bumped {len(py_files)} python + {len(npm_files)} "
        f"npm packages to {args.version} ({total} total)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
