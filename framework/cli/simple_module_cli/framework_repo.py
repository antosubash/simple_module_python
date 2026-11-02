"""Wire a module scaffolded inside the simple_module_python monorepo.

``make new-module`` (via ``scripts/new_module.py``) scaffolds with
``create_module(..., framework_repo=True)`` and then calls
:func:`wire_module` so the new workspace member is a dependency of the dev
host and is collected by pytest and type-checked by ``ty``. Only meaningful
inside this repository, which is why it lives apart from the generic
scaffolders.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

__all__ = [
    "update_host_pyproject",
    "update_release_matrix",
    "update_root_pyproject",
    "wire_module",
]


def _insert_after_last_match(content: str, pattern: str, line_to_insert: str) -> str | None:
    """Insert ``line_to_insert`` on a new line after the last line matching ``pattern``.

    Returns the modified content, or None if no line matched.
    """
    matches = list(re.finditer(pattern, content, re.MULTILINE))
    if not matches:
        return None
    end_of_line = content.find("\n", matches[-1].end())
    if end_of_line == -1:
        end_of_line = len(content)
    return content[: end_of_line + 1] + line_to_insert + content[end_of_line + 1 :]


def update_host_pyproject(root: Path, name: str) -> None:
    """Add the module as a dependency (and workspace source) of ``host/pyproject.toml``."""
    host_toml = root / "host" / "pyproject.toml"
    content = host_toml.read_text()
    # Must be the distribution name the module's own pyproject.toml declares;
    # the bare module name is not a workspace member and `uv sync` rejects it.
    pkg = f"simple_module_{name}"

    if f'"{pkg}"' in content:
        print(f"  host/pyproject.toml already contains {pkg}, skipping")
        return

    original = content
    content = _insert_after_last_match(content, r'^    "[\w-]+",\s*$', f'    "{pkg}",\n') or content
    content = (
        _insert_after_last_match(
            content,
            r"^[\w-]+ = \{ workspace = true \}\s*$",
            f"{pkg} = {{ workspace = true }}\n",
        )
        or content
    )
    if content == original:
        print(f"  warning: no insertion point in host/pyproject.toml for {pkg}", file=sys.stderr)
        return
    host_toml.write_text(content)
    print(f"  updated host/pyproject.toml (added {pkg})")


def update_root_pyproject(root: Path, name: str) -> None:
    """Add the module to ``ty`` extra-paths and pytest ``testpaths`` in the root pyproject."""
    root_toml = root / "pyproject.toml"
    content = root_toml.read_text()
    src_path = f"modules/{name}"
    test_path = f"modules/{name}/tests"

    if f'"{src_path}",' in content and f'"{test_path}"' in content:
        print(f"  root pyproject.toml already contains modules/{name}, skipping")
        return

    original = content
    content = (
        _insert_after_last_match(content, r'^    "modules/[\w/]+",\s*$', f'    "{src_path}",\n')
        or content
    )
    testpaths = list(re.finditer(r'"modules/[\w/]+/tests"', content))
    if testpaths and f'"{test_path}"' not in content:
        last = testpaths[-1]
        content = content[: last.end()] + f', "{test_path}"' + content[last.end() :]

    if content == original:
        print("  warning: no insertion point in pyproject.toml", file=sys.stderr)
        return
    root_toml.write_text(content)
    print("  updated pyproject.toml (added type-check path + test path)")


def update_release_matrix(root: Path, name: str) -> None:
    """Add the module's distribution to the ``publish-pypi`` matrix in ``release.yml``.

    ``scripts/check_metadata.py`` fails until it is listed: an unlisted workspace
    package would build on release and never reach PyPI.
    """
    release = root / ".github" / "workflows" / "release.yml"
    if not release.is_file():
        print("  warning: .github/workflows/release.yml not found", file=sys.stderr)
        return
    pkg = f"simple_module_{name}"
    content = release.read_text()
    if f"- {pkg}\n" in content:
        print(f"  release.yml already lists {pkg}, skipping")
        return
    head, sep, rest = content.partition("publish-pypi:")
    # The matrix list ends where the job's ``environment:`` key starts.
    matrix, env_sep, after = rest.partition("    environment:")
    updated = _insert_after_last_match(
        matrix, r"^          - simple_module_\w+\s*$", f"          - {pkg}\n"
    )
    if not sep or not env_sep or updated is None:
        print("  warning: no publish-pypi matrix in release.yml", file=sys.stderr)
        return
    release.write_text(head + sep + updated + env_sep + after)
    print(f"  updated release.yml (added {pkg} to publish-pypi)")


def wire_module(root: Path, name: str) -> None:
    update_host_pyproject(root, name)
    update_root_pyproject(root, name)
    update_release_matrix(root, name)
