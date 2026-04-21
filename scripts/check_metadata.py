"""Enforce per-package metadata rules across all 17 published packages.

Rules:
  * Every `pyproject.toml` under framework/* and modules/* must have:
      - name starting with "simple_module_"
      - non-placeholder description (not "Add your description here" or empty)
      - readme = "README.md"
      - license = "MIT"
      - "simple-module" in keywords
      - project.urls.Repository set to the canonical GitHub URL
  * Every `package.json` under packages/* must have:
      - name starting with "@simple-module-py/"
      - non-empty description
      - license = "MIT"
      - "simple-module" in keywords
      - repository set
      - publishConfig.access = "public"
      - private not true (or absent)

Exit code 0 on success, 1 on any violation. Prints violations to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import tomlkit

CANONICAL_REPO = "https://github.com/antosubash/simple_module_python"
PLACEHOLDER_DESCRIPTIONS = {"", "Add your description here"}


def check_python_package(pyproject: Path) -> list[str]:
    """Return a list of human-readable violation messages for one pyproject.toml."""
    errors: list[str] = []
    data = tomlkit.parse(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    rel = pyproject

    name = str(project.get("name", ""))
    if not name.startswith("simple_module_"):
        errors.append(f"{rel}: name must start with 'simple_module_' (got '{name}')")

    desc = str(project.get("description", ""))
    if desc in PLACEHOLDER_DESCRIPTIONS:
        errors.append(f"{rel}: description is placeholder or empty")

    if str(project.get("readme", "")) != "README.md":
        errors.append(f"{rel}: readme must be 'README.md'")

    if str(project.get("license", "")) != "MIT":
        errors.append(f"{rel}: license must be 'MIT'")

    keywords = project.get("keywords", [])
    if "simple-module" not in [str(k) for k in keywords]:
        errors.append(f"{rel}: keywords must include 'simple-module'")

    urls = project.get("urls", {})
    if str(urls.get("Repository", "")) != CANONICAL_REPO:
        errors.append(f"{rel}: project.urls.Repository must equal '{CANONICAL_REPO}'")

    return errors


def check_npm_package(package_json: Path) -> list[str]:
    errors: list[str] = []
    data = json.loads(package_json.read_text(encoding="utf-8"))
    rel = package_json

    name = str(data.get("name", ""))
    if not name.startswith("@simple-module-py/"):
        errors.append(f"{rel}: name must start with '@simple-module-py/' (got '{name}')")

    if not str(data.get("description", "")).strip():
        errors.append(f"{rel}: description is empty")

    if str(data.get("license", "")) != "MIT":
        errors.append(f"{rel}: license must be 'MIT'")

    keywords = data.get("keywords", [])
    if "simple-module" not in [str(k) for k in keywords]:
        errors.append(f"{rel}: keywords must include 'simple-module'")

    if not data.get("repository"):
        errors.append(f"{rel}: repository field is required")

    if data.get("private") is True:
        errors.append(f"{rel}: private must not be true (unmark to publish)")

    publish_config = data.get("publishConfig") or {}
    if publish_config.get("access") != "public":
        errors.append(
            f"{rel}: publishConfig.access must be 'public' (scoped packages default to restricted)"
        )

    return errors


def discover_python_packages(root: Path) -> list[Path]:
    found: list[Path] = []
    for base in ("framework", "modules"):
        base_dir = root / base
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir()):
            if not child.is_dir():
                continue
            pyproject = child / "pyproject.toml"
            if pyproject.exists():
                found.append(pyproject)
    return found


def discover_npm_packages(root: Path) -> list[Path]:
    found: list[Path] = []
    packages_dir = root / "packages"
    if not packages_dir.is_dir():
        return found
    for child in sorted(packages_dir.iterdir()):
        if not child.is_dir():
            continue
        pkg = child / "package.json"
        if pkg.exists():
            found.append(pkg)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repo root (default: cwd).",
    )
    args = parser.parse_args(argv)

    root: Path = args.root
    all_errors: list[str] = []
    for pyproject in discover_python_packages(root):
        all_errors.extend(check_python_package(pyproject))
    for pkg in discover_npm_packages(root):
        all_errors.extend(check_npm_package(pkg))

    if all_errors:
        for e in all_errors:
            print(e, file=sys.stderr)
        print(f"\nFAIL: {len(all_errors)} metadata violation(s).", file=sys.stderr)
        return 1
    print("All package metadata OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
