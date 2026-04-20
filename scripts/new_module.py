#!/usr/bin/env python3
"""Scaffold a new module for the Simple Module Python framework.

Usage:
    python scripts/new_module.py <module_name>
    make new-module name=<module_name>

Creates the full module directory structure under modules/<name>/ with all
required files (pyproject.toml, module class, models, service, schemas,
endpoints, tests) and registers the module in host/pyproject.toml and
the root pyproject.toml.
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path

# Make sibling template modules importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _templates_contracts import contracts_init, schemas_py
from _templates_endpoints import api_py, views_py
from _templates_js import package_json, tsconfig_json
from _templates_py import (
    ScaffoldContext,
    deps_py,
    locales_en_json,
    models_py,
    module_py,
    package_init,
    pyproject_toml,
    service_py,
    services_py,
)
from _templates_tests import test_module_py
from _templates_tsx import browse_tsx, create_tsx, edit_tsx

ROOT = Path(__file__).resolve().parent.parent


def validate_name(name: str) -> str:
    """Validate module name: lowercase, alphanumeric, underscores allowed."""
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        print(
            f"Error: Module name '{name}' is invalid. "
            "Use lowercase letters, digits, and underscores. Must start with a letter.",
            file=sys.stderr,
        )
        sys.exit(1)
    return name


def to_class_name(name: str) -> str:
    """Convert snake_case module name to PascalCase class name."""
    return "".join(word.capitalize() for word in name.split("_"))


def to_singular(name: str) -> str:
    """Naive singularization: strip trailing 's' if present."""
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def create_file(path: Path, content: str) -> None:
    """Create a file with the given content, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"))
    print(f"  created {path.relative_to(ROOT)}")


def _build_context(name: str) -> ScaffoldContext:
    singular = to_singular(name)
    return ScaffoldContext(
        name=name,
        class_name=to_class_name(name),
        singular=singular,
        singular_class=to_class_name(singular),
        pkg=name,
    )


def scaffold_module(name: str) -> None:
    """Generate all files for a new module."""
    module_dir = ROOT / "modules" / name
    if module_dir.exists():
        print(f"Error: Module directory modules/{name}/ already exists.", file=sys.stderr)
        sys.exit(1)

    ctx = _build_context(name)
    src_dir = module_dir / ctx.pkg

    print(f"Scaffolding module '{name}'...")

    create_file(module_dir / "pyproject.toml", pyproject_toml(ctx))
    create_file(module_dir / "package.json", package_json(ctx))
    create_file(module_dir / "tsconfig.json", tsconfig_json(ctx))
    create_file(src_dir / "__init__.py", package_init(ctx))
    create_file(src_dir / "py.typed", "")
    create_file(src_dir / "module.py", module_py(ctx))
    create_file(src_dir / "services.py", services_py(ctx))
    create_file(src_dir / "models.py", models_py(ctx))
    create_file(src_dir / "contracts" / "__init__.py", contracts_init(ctx))
    create_file(src_dir / "contracts" / "schemas.py", schemas_py(ctx))
    create_file(src_dir / "service.py", service_py(ctx))
    create_file(src_dir / "deps.py", deps_py(ctx))
    create_file(src_dir / "endpoints" / "__init__.py", "")
    create_file(src_dir / "endpoints" / "api.py", api_py(ctx))
    create_file(src_dir / "endpoints" / "views.py", views_py(ctx))
    create_file(src_dir / "pages" / "Browse.tsx", browse_tsx(ctx))
    create_file(src_dir / "pages" / "Create.tsx", create_tsx(ctx))
    create_file(src_dir / "pages" / "Edit.tsx", edit_tsx(ctx))
    create_file(src_dir / "locales" / "en.json", locales_en_json(ctx))
    create_file(module_dir / "tests" / f"test_{name}.py", test_module_py(ctx))


def _insert_after_last_match(content: str, pattern: str, line_to_insert: str) -> str | None:
    """Insert ``line_to_insert`` on a new line after the last line matching ``pattern``.

    Returns the modified content, or None if no line matched.
    """
    matches = list(re.finditer(pattern, content, re.MULTILINE))
    if not matches:
        return None
    last = matches[-1]
    end_of_line = content.find("\n", last.end())
    if end_of_line == -1:
        end_of_line = len(content)
    return content[: end_of_line + 1] + line_to_insert + content[end_of_line + 1 :]


def update_host_pyproject(name: str) -> None:
    """Add the new module as a dependency in host/pyproject.toml."""
    host_toml = ROOT / "host" / "pyproject.toml"
    content = host_toml.read_text()
    pkg = name.replace("_", "-")

    if f'"{pkg}"' in content:
        print(f"  host/pyproject.toml already contains {pkg}, skipping")
        return

    original = content

    # Add to [project] dependencies — insert after last module dep line
    result = _insert_after_last_match(
        content,
        r'^    "[\w-]+",\s*$',
        f'    "{pkg}",\n',
    )
    if result:
        content = result

    # Add to [tool.uv.sources] — insert after last workspace source line
    result = _insert_after_last_match(
        content,
        r"^[\w-]+ = \{ workspace = true \}\s*$",
        f"{pkg} = {{ workspace = true }}\n",
    )
    if result:
        content = result

    if content == original:
        print(
            f"  warning: could not find insertion point in host/pyproject.toml for {pkg}",
            file=sys.stderr,
        )
        return

    host_toml.write_text(content)
    print(f"  updated host/pyproject.toml (added {pkg})")


def update_root_pyproject(name: str) -> None:
    """Add the module to type-checking paths and test paths in root pyproject.toml."""
    root_toml = ROOT / "pyproject.toml"
    content = root_toml.read_text()
    src_path = f"modules/{name}"
    test_path = f"modules/{name}/tests"

    if f'"{src_path}",' in content and f'"{test_path}"' in content:
        print(f"  root pyproject.toml already contains modules/{name}, skipping")
        return

    original = content

    # Add to [tool.ty.environment] extra-paths — insert after last "modules/*" entry
    result = _insert_after_last_match(
        content,
        r'^    "modules/[\w/]+",\s*$',
        f'    "{src_path}",\n',
    )
    if result:
        content = result

    # Append after the last "modules/*/tests" entry, before the closing ]
    testpath_matches = list(re.finditer(r'"modules/[\w/]+/tests"', content))
    if testpath_matches and f'"{test_path}"' not in content:
        last = testpath_matches[-1]
        content = content[: last.end()] + f', "{test_path}"' + content[last.end() :]

    if content == original:
        print(
            "  warning: could not find insertion point in pyproject.toml",
            file=sys.stderr,
        )
        return

    root_toml.write_text(content)
    print("  updated pyproject.toml (added type-check path + test path)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scaffold a new module for Simple Module Python",
    )
    parser.add_argument(
        "name",
        help="Module name in snake_case (e.g. 'orders', 'blog_posts')",
    )
    args = parser.parse_args()

    name = validate_name(args.name)

    scaffold_module(name)
    update_host_pyproject(name)
    update_root_pyproject(name)

    print()
    print(f"Module '{name}' scaffolded successfully!")
    print()
    print("Next steps:")
    print("  1. Run 'uv sync --all-packages && npm install' to install the new module")
    print(f"  2. Edit modules/{name}/{name}/models.py to define your domain model")
    print("  3. Update schemas, service, and endpoints to match your model")
    print(f"  4. Run 'make migration msg=\"add {name} tables\"' to create a migration")
    print("  5. Run 'make test' to verify everything works")


if __name__ == "__main__":
    main()
